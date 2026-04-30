import os
import time
import struct
import grpc
import psycopg2
import sys
from dotenv import load_dotenv

load_dotenv()

# Importa stubs gRPC
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc
from maas_client import MaaSMemory

# Configurações de Rede e Banco
MAAS_BUFFER_SIZE = int(os.getenv("MAAS_BUFFER_SIZE", 10485760))
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "100.114.106.28:50051")
DB_CONNECTION = os.getenv("DB_CONNECTION")

# Struct de 44 bytes: Lat, Lon, Temp, FRP, Conf, Type, ID
STRUCT_FORMAT = '=ddddiii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)

# Thresholds para Análise de Dados / Insight
TEMP_ANOMALY_THRESHOLD = 330.0 # Kelvin (aprox 57ºC de emissão radiativa - foco vivo)
CONFIDENCE_THRESHOLD = 80 # Apenas alta confiança (evita falsos positivos)

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

def process_data():
    conn = get_db_connection()
    
    # Lê metadados dinâmicos
    shm_name, alloc_id, buffer_size = get_meta_info()
    
    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)
    mm = get_remote_memory(stub, alloc_id, buffer_size)
            
    print("[+] Conectado ao MaaS Buffer via REDE. Iniciando Motor Analítico (Batch Mode)...")
    
    last_offset = 0
    processed_ids = set() # Evita duplicatas
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
                    processed_ids.clear() 

                if record_id == 0 or record_id in processed_ids:
                    continue
                    
                processed_ids.add(record_id)
                if len(processed_ids) > MAX_PROCESSED_IDS:
                    processed_ids.pop() # Remove o mais antigo (LRU aproximado)
                
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

            # 2. INSERÇÃO EM LOTE NO BANCO (BATCH INSERT)
            if records_to_process and conn and not conn.closed:
                with conn.cursor() as cursor:
                    for r in records_to_process:
                        # Inserção da leitura básica com FRP e sat_type (CORRIGIDO: Ordem das colunas)
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.sensor_readings 
                            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
                            VALUES (1, %s, %s, %s, %s, %s, %s) RETURNING id;
                        """, (r[0], r[1], r[2], r[3], r[5], r[4]))
                        
                        reading_id = cursor.fetchone()[0]
                        
                        # Inserção no histórico
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.alerts_history 
                            (reading_id, alert_type, severity, description)
                            VALUES (%s, %s, %s, %s);
                        """, (reading_id, r[6], r[7], r[8]))
                        
                conn.commit()
                print(f"[*] Batch de {len(records_to_process)} registros processado com sucesso.")
            elif not records_to_process:
                time.sleep(1) # Aguarda novos dados
            else:
                print("[-] Banco desconectado. Reconectando...")
                conn = get_db_connection()

        except Exception as e:
            print(f"[-] Erro crítico: {e}")
            time.sleep(5)
            shm_name, alloc_id, buffer_size = get_meta_info()
            mm = get_remote_memory(stub, alloc_id, buffer_size)
            last_offset = 0

if __name__ == "__main__":
    process_data()
