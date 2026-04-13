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

# Struct de 32 bytes: Latitude (double), Longitude (double), Temperatura (double), Confiança (int), ID (int)
STRUCT_FORMAT = '=dddii'
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
            
    print("[+] Conectado ao MaaS Buffer via REDE. Iniciando Motor Analítico...")
    
    last_offset = 0
    processed_ids = set() # Evita processar a mesma leitura mais de uma vez
    
    while True:
        try:
            mm.seek(last_offset)
            raw_data = mm.read(RECORD_SIZE)
            
            # Validação de bloco (sem dados novos na posição)
            if not raw_data or len(raw_data) < RECORD_SIZE or raw_data == b'\x00' * RECORD_SIZE:
                time.sleep(1) 
                continue

            # Deserialização rápida em C-struct -> Python Tuple
            lat, lon, temp, conf, record_id = struct.unpack(STRUCT_FORMAT, raw_data)
            
            # Atualiza ponteiro do buffer circular
            last_offset += RECORD_SIZE
            if last_offset >= buffer_size:
                last_offset = 0
                processed_ids.clear() 
                
            if record_id == 0 or record_id in processed_ids:
                continue
                
            processed_ids.add(record_id)
            
            # --- CIÊNCIA DE DADOS: DETECÇÃO DE ANOMALIA ---
            if conf >= CONFIDENCE_THRESHOLD and temp >= TEMP_ANOMALY_THRESHOLD:
                print(f"[!] INSIGHT: Anomalia Térmica Detectada! Lat {lat:.4f}, Lon {lon:.4f}, Temp {temp}K, Conf {conf}%")
                
                if conn and not conn.closed:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.sensor_readings 
                            (sensor_id, latitude, longitude, temperature_k, confidence)
                            VALUES (1, %s, %s, %s, %s) RETURNING id;
                        """, (lat, lon, temp, conf))
                        
                        reading_id = cursor.fetchone()[0]
                        
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.alerts_history 
                            (reading_id, alert_type, severity, description)
                            VALUES (%s, 'THERMAL_ANOMALY', 'CRITICAL', 'Foco detectado em tempo real via MaaS Network.');
                        """, (reading_id,))
                        
                    conn.commit()
                else:
                    print("[-] Banco de dados desconectado. Tentando restabelecer conexão...")
                    conn = get_db_connection()

        except Exception as e:
            print(f"[-] Erro de processamento ou o Buffer foi destruído: {e}")
            time.sleep(5)
            # Tentativa de recuperação
            shm_name, alloc_id, buffer_size = get_meta_info()
            mm = get_remote_memory(stub, alloc_id, buffer_size)
            last_offset = 0

if __name__ == "__main__":
    process_data()
