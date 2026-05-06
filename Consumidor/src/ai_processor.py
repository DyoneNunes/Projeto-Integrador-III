"""
Sentinela Ambiental - AI Processor (LightGBM)
Lê feature vectors do MaaS Buffer B, roda inferência e grava predições no Buffer C.
Todo fluxo de dados passa pelo MaaS (memória desagregada via gRPC).
"""
import os
import sys
import time
import struct
import grpc
import psycopg2
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# Importa stubs gRPC
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc
from maas_client import MaaSMemory

# Configurações
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "100.114.106.28:50051")
MAAS_DB_URL = os.getenv("MAAS_DB_URL")
DB_CONNECTION = os.getenv("DB_CONNECTION")
MODEL_PATH = os.getenv("MODEL_PATH", "/app/models/sentinela_v1.txt")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1.0.0")
TENANT_NAME = os.getenv("TENANT_NAME", "Sentinela Ambiental")

# Buffer B (input - feature vectors do data_processor)
FEATURE_FORMAT = '=iffffffff'  # reading_id + 8 floats = 36 bytes
FEATURE_SIZE = struct.calcsize(FEATURE_FORMAT)
BUFFER_B_META_FILE = "/dev/shm/maas_features_info.txt"

# Buffer C (output - predições)
PREDICTION_FORMAT = '=iiffff'
PREDICTION_SIZE = struct.calcsize(PREDICTION_FORMAT)
BUFFER_C_SIZE = int(os.getenv("MAAS_BUFFER_C_SIZE", 20971520))  # 20MB
BUFFER_C_META_FILE = "/dev/shm/maas_predictions_info.txt"

# Processamento
BATCH_SIZE = 50
PREDICTION_THRESHOLD = 0.5


def load_model():
    """Carrega o modelo LightGBM do disco."""
    try:
        import lightgbm as lgb
        model = lgb.Booster(model_file=MODEL_PATH)
        print(f"[+] Modelo LightGBM carregado: {MODEL_PATH} ({MODEL_VERSION})")
        return model
    except FileNotFoundError:
        print(f"[!] Modelo não encontrado em {MODEL_PATH}. Usando modo fallback (threshold).")
        return None
    except Exception as e:
        print(f"[!] Erro ao carregar modelo: {e}. Usando modo fallback.")
        return None


def fallback_predict(features_batch):
    """
    Predição fallback quando o modelo treinado não está disponível.
    Temperatura é pré-requisito (gate) — sem evidência térmica, não é fogo.
    """
    predictions = []
    for feat in features_batch:
        lat, lng, frp, temp_k, conf, hour, month, neighbors = feat

        # Gate: sem temperatura mínima, impossível ser fogo
        if temp_k < 310.0:
            predictions.append(0.05)
            continue

        score = 0.0

        # Temperatura (fator principal — até 0.50)
        if temp_k >= 360.0:
            score += 0.50
        elif temp_k >= 330.0:
            score += 0.35
        elif temp_k >= 310.0:
            score += 0.15

        # Confiança (fator secundário — até 0.20)
        if conf >= 90:
            score += 0.20
        elif conf >= 80:
            score += 0.10

        # FRP (fator terciário — até 0.20)
        if frp >= 50.0:
            score += 0.20
        elif frp >= 10.0:
            score += 0.10

        # Contexto temporal (bônus pequeno — até 0.10)
        if 12 <= hour <= 18:
            score += 0.05
        if 6 <= month <= 10:
            score += 0.05

        score = min(score, 1.0)
        predictions.append(score)
    return np.array(predictions)


def get_db_connection():
    """Conecta ao PostgreSQL com retentativas."""
    retries = 5
    while retries > 0:
        try:
            conn = psycopg2.connect(DB_CONNECTION)
            print("[+] AI Processor conectado ao PostgreSQL.")
            return conn
        except Exception as e:
            print(f"[-] Erro DB ({retries} tentativas): {e}")
            retries -= 1
            time.sleep(3)
    return None


def wait_for_buffer_b_meta() -> tuple:
    """Aguarda o data_processor criar o Buffer B."""
    print("[*] Aguardando Buffer B (feature vectors do data_processor)...")
    while True:
        if os.path.exists(BUFFER_B_META_FILE):
            try:
                with open(BUFFER_B_META_FILE, "r") as f:
                    lines = f.read().strip().split("\n")
                if len(lines) >= 3:
                    name = lines[0]
                    alloc_id = lines[1]
                    size = int(lines[2])
                    print(f"[+] Buffer B encontrado: alloc_id={alloc_id}, size={size}")
                    return name, alloc_id, size
            except Exception as e:
                print(f"[-] Erro lendo meta Buffer B: {e}")
        time.sleep(2)


def get_or_create_tenant() -> str:
    """Obtém o tenant_id real do banco MaaS (mesmo método do ingestor)."""
    retries = 10
    while retries > 0:
        try:
            conn = psycopg2.connect(MAAS_DB_URL)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT tenant_id FROM public.tenant WHERE name = %s LIMIT 1", (TENANT_NAME,))
                row = cur.fetchone()
                if row:
                    tenant_id = str(row[0])
                    conn.close()
                    return tenant_id
                cur.execute("INSERT INTO public.tenant (name, plan, status) VALUES (%s, 'Developer', 'active') RETURNING tenant_id", (TENANT_NAME,))
                tenant_id = str(cur.fetchone()[0])
                conn.close()
                return tenant_id
        except Exception as e:
            retries -= 1
            time.sleep(3)
    raise RuntimeError("Falha ao obter tenant_id do banco MaaS.")


def allocate_buffer_c(stub, tenant_id: str) -> MaaSMemory | None:
    """Aloca Buffer C no MaaS usando o tenant_id real (mesmo método do Buffer A)."""
    try:
        request = maas_pb2.AllocateRequest(
            tenant_id=tenant_id,
            size_bytes=BUFFER_C_SIZE
        )
        response = stub.Allocate(request, timeout=10)
        alloc_id = response.allocation_id

        with open(BUFFER_C_META_FILE, "w") as f:
            f.write(f"predictions_buffer\n{alloc_id}\n{BUFFER_C_SIZE}\n")

        print(f"[+] Buffer C alocado: alloc_id={alloc_id}, size={BUFFER_C_SIZE}")
        return MaaSMemory(stub, alloc_id, BUFFER_C_SIZE)
    except Exception as e:
        print(f"[-] Falha ao alocar Buffer C: {e}")
        return None


def compute_urgency(prob, frp, temp_k):
    """Calcula score de urgência (0-1) combinando probabilidade, FRP e temperatura."""
    frp_norm = min(frp / 200.0, 1.0)
    temp_norm = min(max(temp_k - 300, 0) / 100.0, 1.0)
    return 0.5 * prob + 0.3 * frp_norm + 0.2 * temp_norm


def run():
    conn = get_db_connection()

    # Espera Buffer B ficar disponível
    _, buffer_b_alloc_id, buffer_b_size = wait_for_buffer_b_meta()

    # Conecta ao MaaS
    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)

    mm_in = MaaSMemory(stub, buffer_b_alloc_id, buffer_b_size)

    # Obtém tenant_id real e aloca Buffer C (mesmo método do Buffer A)
    tenant_id = get_or_create_tenant()
    mm_out = allocate_buffer_c(stub, tenant_id)

    # Carrega modelo
    model = load_model()

    print("[+] AI Processor iniciado. Consumindo features do Buffer B...")

    read_offset = 0
    write_offset = 0
    record_counter = 0

    while True:
        try:
            batch_features = []
            batch_reading_ids = []

            # 1. LÊ BATCH DO BUFFER B
            for _ in range(BATCH_SIZE):
                mm_in.seek(read_offset)
                raw = mm_in.read(FEATURE_SIZE)

                if not raw or len(raw) < FEATURE_SIZE or raw == b'\x00' * FEATURE_SIZE:
                    break

                unpacked = struct.unpack(FEATURE_FORMAT, raw)
                reading_id = unpacked[0]
                feat = unpacked[1:]  # (lat, lng, frp, temp_k, conf, hour, month, neighbors)
                batch_reading_ids.append(reading_id)
                batch_features.append(feat)

                read_offset += FEATURE_SIZE
                if read_offset >= buffer_b_size:
                    read_offset = 0

            if not batch_features:
                time.sleep(2)
                continue

            # 2. INFERÊNCIA
            features_array = np.array(batch_features, dtype=np.float64)

            if model is not None:
                probabilities = model.predict(features_array)
            else:
                probabilities = fallback_predict(batch_features)

            # 3. GRAVA PREDIÇÕES NO BUFFER C + POSTGRESQL
            predictions_to_insert = []

            for i, (feat, prob) in enumerate(zip(batch_features, probabilities)):
                lat, lng, frp, temp_k, conf, hour, month, neighbors = feat
                record_counter += 1

                pred_class = 1 if prob >= PREDICTION_THRESHOLD else 0
                urgency = compute_urgency(prob, frp, temp_k)

                # Empacota e grava no Buffer C
                if mm_out:
                    pred_record = struct.pack(
                        PREDICTION_FORMAT,
                        record_counter, pred_class,
                        float(prob), float(urgency),
                        float(lat), float(lng)
                    )
                    try:
                        mm_out.seek(write_offset)
                        mm_out.write(pred_record)
                        write_offset += PREDICTION_SIZE
                        if write_offset >= BUFFER_C_SIZE:
                            write_offset = 0
                    except Exception as e:
                        print(f"[-] Erro gravando Buffer C: {e}")

                predictions_to_insert.append((
                    batch_reading_ids[i], pred_class, float(prob), float(urgency)
                ))

            # 4. PERSISTE NO POSTGRESQL (usando reading_id direto, sem race condition)
            if predictions_to_insert and conn and not conn.closed:
                try:
                    with conn.cursor() as cur:
                        for reading_id, pred_class, prob, urgency in predictions_to_insert:
                            cur.execute("""
                                INSERT INTO sentinela_ambiental.ai_predictions
                                (reading_id, model_version, prediction_class, prediction_probability, urgency_score)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (reading_id) DO NOTHING
                            """, (reading_id, MODEL_VERSION, pred_class, prob, urgency))

                    conn.commit()
                except Exception as e:
                    print(f"[-] Erro ao inserir predições no DB: {e}")
                    conn.rollback()
                    conn = get_db_connection()

            print(f"[*] AI Batch: {len(batch_features)} features → "
                  f"{sum(1 for p in probabilities if p >= PREDICTION_THRESHOLD)} focos detectados "
                  f"(max_prob={max(probabilities):.3f})")

        except Exception as e:
            print(f"[-] Erro crítico no AI Processor: {e}")
            time.sleep(5)
            try:
                channel.close()
                channel = grpc.insecure_channel(MAAS_GRPC_HOST)
                stub = maas_pb2_grpc.MemoryServiceStub(channel)
                _, buffer_b_alloc_id, buffer_b_size = wait_for_buffer_b_meta()
                mm_in = MaaSMemory(stub, buffer_b_alloc_id, buffer_b_size)
                read_offset = 0
            except Exception as e_retry:
                print(f"[-] Falha na reconexão: {e_retry}")
                time.sleep(10)
                continue


if __name__ == "__main__":
    run()
