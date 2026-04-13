import os
import time
import struct
import mmap
import posix_ipc
import psycopg2
from dotenv import load_dotenv

load_dotenv()

MAAS_BUFFER_SIZE = int(os.getenv("MAAS_BUFFER_SIZE", 10485760))
DB_CONNECTION = os.getenv("DB_CONNECTION")

# Struct de 32 bytes: Latitude (double), Longitude (double), Temperatura (double), Confiança (int), ID (int)
STRUCT_FORMAT = '=dddii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)

# Thresholds para Análise de Dados / Insight
TEMP_ANOMALY_THRESHOLD = 330.0 # Kelvin (aprox 57ºC de emissão radiativa - foco vivo)
CONFIDENCE_THRESHOLD = 80 # Apenas alta confiança (evita falsos positivos de reflexos solares)

# Caminho do arquivo de metadados escrito pelo ingestor
META_FILE = "/dev/shm/maas_shm_info.txt"

def get_shm_name_from_meta() -> tuple[str, int]:
    """
    Lê o nome da SHM e o tamanho a partir do arquivo de metadados
    escritos pelo ingestor após o handshake com o MaaS.
    """
    print("[*] Aguardando metadados do Ingestor (handshake MaaS)...")
    while True:
        if os.path.exists(META_FILE):
            try:
                with open(META_FILE, "r") as f:
                    lines = f.read().strip().split("\n")
                if len(lines) >= 3:
                    shm_name = lines[0]
                    size = int(lines[2])
                    print(f"[+] Metadados recebidos: shm_name={shm_name}, size={size}")
                    return shm_name, size
            except Exception as e:
                print(f"[-] Erro ao ler metadados: {e}")
        time.sleep(2)

def get_db_connection():
    """
    Tenta conectar ao banco de dados com múltiplas retentativas para suportar o tempo de subida do Docker DNS.
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

def get_shared_memory(shm_name: str, size: int) -> mmap.mmap:
    """
    Acessa a memória em RAM criada pelo MaaS Core e populada pelo Módulo Ingestor.
    Modo ACCESS_READ para evitar concorrência de escrita.
    """
    try:
        # Abre a memória sem a flag O_CREAT (deve existir)
        memory = posix_ipc.SharedMemory(shm_name)
        map_file = mmap.mmap(memory.fd, memory.size, access=mmap.ACCESS_READ)
        memory.close_fd()
        return map_file
    except posix_ipc.ExistentialError:
        return None
    except Exception as e:
        print(f"[-] Erro fatal de memória POSIX: {e}")
        return None

def process_data():
    conn = get_db_connection()
    
    # Lê o SHM name dinâmico dos metadados escritos pelo ingestor
    shm_name, buffer_size = get_shm_name_from_meta()
    
    mm = None
    # Aguarda o ingestor criar o bloco via MaaS
    while mm is None:
        mm = get_shared_memory(shm_name, buffer_size)
        if mm is None:
            print("[*] Aguardando alocação da RAM pelo Ingestor (MaaS)...")
            time.sleep(2)
            
    print("[+] Conectado ao MaaS Buffer. Iniciando Motor Analítico (Latência Zero)...")
    
    last_offset = 0
    processed_ids = set() # Evita processar a mesma leitura mais de uma vez
    
    while True:
        try:
            mm.seek(last_offset)
            raw_data = mm.read(RECORD_SIZE)
            
            # Validação de bloco (sem dados novos na posição)
            if not raw_data or len(raw_data) < RECORD_SIZE or raw_data == b'\x00' * RECORD_SIZE:
                time.sleep(1) # Aguarda o Ingestor gravar mais dados
                continue

            # Deserialização rápida em C-struct -> Python Tuple
            lat, lon, temp, conf, record_id = struct.unpack(STRUCT_FORMAT, raw_data)
            
            # Atualiza ponteiro do buffer circular
            last_offset += RECORD_SIZE
            if last_offset >= buffer_size:
                last_offset = 0
                processed_ids.clear() # Limpa histórico para nova rotação
                
            if record_id == 0 or record_id in processed_ids:
                continue
                
            processed_ids.add(record_id)
            
            # --- CIÊNCIA DE DADOS: DETECÇÃO DE ANOMALIA ---
            if conf >= CONFIDENCE_THRESHOLD and temp >= TEMP_ANOMALY_THRESHOLD:
                print(f"[!] INSIGHT: Anomalia Térmica Detectada! Lat {lat:.4f}, Lon {lon:.4f}, Temp {temp}K, Conf {conf}%")
                
                # Persistência Inteligente (Salvar no banco relacional apenas o insight crítico)
                if conn and not conn.closed:
                    with conn.cursor() as cursor:
                        # 1. Salvar leitura filtrada
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.sensor_readings 
                            (sensor_id, latitude, longitude, temperature_k, confidence)
                            VALUES (1, %s, %s, %s, %s) RETURNING id;
                        """, (lat, lon, temp, conf))
                        
                        reading_id = cursor.fetchone()[0]
                        
                        # 2. Gerar alerta
                        cursor.execute("""
                            INSERT INTO sentinela_ambiental.alerts_history 
                            (reading_id, alert_type, severity, description)
                            VALUES (%s, 'THERMAL_ANOMALY', 'CRITICAL', 'Foco de incêndio detectado em tempo real via MaaS.');
                        """, (reading_id,))
                        
                    conn.commit()
                else:
                    print("[-] Banco de dados desconectado. Tentando restabelecer conexão...")
                    conn = get_db_connection()

        except Exception as e:
            print(f"[-] Erro de processamento ou o Buffer foi destruído: {e}")
            time.sleep(3)
            # Tentativa de recuperação: relê metadados e reconecta à SHM
            mm = None
            shm_name, buffer_size = get_shm_name_from_meta()
            while mm is None:
                mm = get_shared_memory(shm_name, buffer_size)
                if mm is None:
                    time.sleep(2)
            last_offset = 0

if __name__ == "__main__":
    process_data()
