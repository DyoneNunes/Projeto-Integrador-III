import os
import sys
import time
import struct
import grpc
import psycopg2
from collections import OrderedDict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Importa stubs gRPC
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc
from maas_client import MaaSMemory

# Configurações de Rede e Banco
MAAS_BUFFER_SIZE = int(os.getenv("MAAS_BUFFER_SIZE", 104857600))
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "100.114.106.28:50051")
MAAS_DB_URL = os.getenv("MAAS_DB_URL")
DB_CONNECTION = os.getenv("DB_CONNECTION")
TENANT_NAME = os.getenv("TENANT_NAME", "Sentinela Ambiental")

# Struct de 44 bytes: Lat, Lon, Temp, FRP, Conf, Type, ID
STRUCT_FORMAT = '=ddddiii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)

# Struct do Buffer B (Feature Vector - 36 bytes): reading_id, lat, lng, frp, temp_k, conf, hour, month, neighbor_density
FEATURE_FORMAT = '=iffffffff'
FEATURE_SIZE = struct.calcsize(FEATURE_FORMAT)

# Thresholds para Análise de Dados / Insight
TEMP_ANOMALY_THRESHOLD = 330.0 # Kelvin (aprox 57ºC de emissão radiativa - foco vivo)
CONFIDENCE_THRESHOLD = 80 # Apenas alta confiança (evita falsos positivos)

# Configuração do Buffer B (features para IA)
BUFFER_B_SIZE = int(os.getenv("MAAS_BUFFER_B_SIZE", 52428800))  # 50MB
BUFFER_B_META_FILE = "/dev/shm/maas_features_info.txt"

# Caminho do arquivo de metadados escrito pelo ingestor
META_FILE = "/dev/shm/maas_shm_info.txt"

def get_meta_info() -> tuple[str, str, int]:
    """
    Lê o nome da SHM, allocation_id e o tamanho a partir do arquivo de metadados.
    """
    print("[*] Aguardando metadados do Ingestor (handshake MaaS)...")
    while True:
        if os.path.exists(META_FILE):
            try:
                with open(META_FILE, "r") as f:
                    lines = f.read().strip().split("\n")
                if len(lines) >= 3:
                    shm_name = lines[0]
                    alloc_id = lines[1]
                    size = int(lines[2])
                    print(f"[+] Metadados recebidos: alloc_id={alloc_id}, size={size}")
                    return shm_name, alloc_id, size
            except Exception as e:
                print(f"[-] Erro ao ler metadados: {e}")
        time.sleep(2)

def get_db_connection():
    """
    Tenta conectar ao banco de dados com múltiplas retentativas.
    """
    retries = 5
    while retries > 0:
        try:
            conn = psycopg2.connect(DB_CONNECTION)
            print("[+] Conexão com o PostgreSQL estabelecida com sucesso.")
            return conn
        except Exception as e:
            print(f"[-] Erro ao conectar no DB ({retries} tentativas restantes): {e}")
            retries -= 1
            time.sleep(3)
    return None

def get_remote_memory(stub, alloc_id: str, size: int) -> MaaSMemory:
    """
    Inicializa a abstração de memória via rede.
    """
    return MaaSMemory(stub, alloc_id, size)


def get_or_create_tenant() -> str:
    """
    Obtém o tenant_id real do banco MaaS (mesmo método do ingestor).
    """
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


def allocate_buffer_b(stub, tenant_id: str) -> MaaSMemory | None:
    """
    Aloca o Buffer B no MaaS usando o tenant_id real (mesmo método do Buffer A).
    Grava metadados em arquivo para o ai_processor encontrar.
    """
    try:
        request = maas_pb2.AllocateRequest(
            tenant_id=tenant_id,
            size_bytes=BUFFER_B_SIZE
        )
        response = stub.Allocate(request, timeout=10)
        alloc_id = response.allocation_id

        # Persiste metadados do Buffer B
        with open(BUFFER_B_META_FILE, "w") as f:
            f.write(f"features_buffer\n{alloc_id}\n{BUFFER_B_SIZE}\n")

        print(f"[+] Buffer B alocado: alloc_id={alloc_id}, size={BUFFER_B_SIZE}")
        return MaaSMemory(stub, alloc_id, BUFFER_B_SIZE)
    except Exception as e:
        print(f"[-] Falha ao alocar Buffer B: {e}")
        return None

def count_neighbors(records, idx, radius_deg=0.5):
    """Conta pontos dentro de ~50km (0.5 graus) do ponto idx."""
    lat0, lon0 = records[idx][0], records[idx][1]
    count = 0
    for j, r in enumerate(records):
        if j == idx:
            continue
        dlat = r[0] - lat0
        dlon = r[1] - lon0
        if dlat * dlat + dlon * dlon <= radius_deg * radius_deg:
            count += 1
    return float(count)


def process_data():
    conn = get_db_connection()

    # Lê metadados dinâmicos
    shm_name, alloc_id, buffer_size = get_meta_info()

    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)
    mm = get_remote_memory(stub, alloc_id, buffer_size)

    # Obtém tenant_id real e aloca Buffer B (mesmo método do Buffer A)
    tenant_id = get_or_create_tenant()
    mm_features = allocate_buffer_b(stub, tenant_id)
    feature_offset = 0

    print("[+] Conectado ao MaaS Buffer via REDE. Iniciando Motor Analítico (Batch Mode)...")

    last_offset = 0
    processed_ids = OrderedDict()  # LRU para evitar duplicatas
    MAX_PROCESSED_IDS = 100000
    BATCH_SIZE = 50
    
    while True:
        try:
            records_to_process = []
            
            # 1. COLETA DE LOTE (BATCH READ)
            for _ in range(BATCH_SIZE):
                mm.seek(last_offset)
                raw_data = mm.read(RECORD_SIZE)
                
                if not raw_data or len(raw_data) < RECORD_SIZE or raw_data == b'\x00' * RECORD_SIZE:
                    break # Fim dos novos dados por agora
                
                lat, lon, temp, frp, conf, sat_type, record_id = struct.unpack(STRUCT_FORMAT, raw_data)
                
                # Avança offset
                last_offset += RECORD_SIZE
                if last_offset >= buffer_size:
                    last_offset = 0

                if record_id == 0 or record_id in processed_ids:
                    continue

                processed_ids[record_id] = True
                if len(processed_ids) > MAX_PROCESSED_IDS:
                    processed_ids.popitem(last=False)  # Remove o mais antigo (LRU)
                
                # Análise e Categorização (Data Science & Integrity)
                # Filtro principal: Apenas fogo presumido (sat_type=0) e alta confiança
                is_fire = (sat_type == 0)
                is_anomaly = (conf >= CONFIDENCE_THRESHOLD and temp >= TEMP_ANOMALY_THRESHOLD and is_fire)
                
                alert_type = 'THERMAL_ANOMALY' if is_anomaly else 'AMBIENT_READING'
                severity = 'CRITICAL' if is_anomaly else 'INFO'
                
                if not is_fire:
                    description = f"Fonte estática détectada (Tipo {sat_type}). Ignorado para alertas críticos."
                    severity = 'LOW'
                elif is_anomaly:
                    description = f"Foco crítico detectado (FRP: {frp:.2f})."
                else:
                    description = 'Leitura térmica estável.'
                
                records_to_process.append((lat, lon, temp, frp, conf, sat_type, alert_type, severity, description))

            # 2. INSERÇÃO EM LOTE NO BANCO + ESCRITA DE FEATURES NO BUFFER B
            if records_to_process and conn and not conn.closed:
                now = datetime.now()
                hour = float(now.hour)
                month = float(now.month)

                with conn.cursor() as cursor:
                    for i, r in enumerate(records_to_process):
                        # Inserção da leitura básica com FRP e sat_type
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.sensor_readings
                            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
                            VALUES (1, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ROUND(latitude::numeric, 3), ROUND(longitude::numeric, 3), ROUND(temperature_k::numeric, 1))
                            DO NOTHING
                            RETURNING id;
                        """, (r[0], r[1], r[2], r[3], r[5], r[4]))

                        row = cursor.fetchone()
                        if row is None:
                            continue  # Duplicata, pula alert e feature
                        reading_id = row[0]

                        # Inserção no histórico
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.alerts_history
                            (reading_id, alert_type, severity, description)
                            VALUES (%s, %s, %s, %s);
                        """, (reading_id, r[6], r[7], r[8]))

                        # Escrita de feature no Buffer B (com reading_id para rastreabilidade)
                        if mm_features:
                            lat, lon, temp, frp, conf = r[0], r[1], r[2], r[3], r[4]
                            neighbor_density = count_neighbors(records_to_process, i)
                            feature_vec = struct.pack(
                                FEATURE_FORMAT,
                                int(reading_id), float(lat), float(lon), float(frp), float(temp),
                                float(conf), hour, month, neighbor_density
                            )
                            try:
                                mm_features.seek(feature_offset)
                                mm_features.write(feature_vec)
                                feature_offset += FEATURE_SIZE
                                if feature_offset >= BUFFER_B_SIZE:
                                    feature_offset = 0  # Circular
                            except Exception as e:
                                print(f"[-] Erro ao gravar feature no Buffer B: {e}")

                conn.commit()
                print(f"[*] Batch de {len(records_to_process)} registros processado com sucesso.")

            elif not records_to_process:
                time.sleep(1) # Aguarda novos dados
            else:
                print("[-] Banco desconectado. Reconectando...")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_db_connection()

        except Exception as e:
            print(f"[-] Erro crítico: {e}")
            time.sleep(5)
            try:
                channel.close()
                channel = grpc.insecure_channel(MAAS_GRPC_HOST)
                stub = maas_pb2_grpc.MemoryServiceStub(channel)
                shm_name, alloc_id, buffer_size = get_meta_info()
                mm = get_remote_memory(stub, alloc_id, buffer_size)
                last_offset = 0
            except Exception as e_retry:
                print(f"[-] Falha na reconexão: {e_retry}")
                time.sleep(10)
                continue

if __name__ == "__main__":
    process_data()
