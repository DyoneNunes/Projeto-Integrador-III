import os
import sys
import time
import struct
import requests
import grpc
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Importa stubs gRPC gerados pelo entrypoint.sh
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc
from maas_client import MaaSMemory

NASA_MAP_KEY = os.getenv("NASA_MAP_KEY")
MAAS_BUFFER_SIZE = int(os.getenv("MAAS_BUFFER_SIZE", 10485760))
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "maas-core:50051")
MAAS_DB_URL = os.getenv("MAAS_DB_URL", "postgresql://postgres:postgres@maas-db:5432/postgres")
DB_CONNECTION = os.getenv("DB_CONNECTION", "postgresql://postgres:password_sentinela@db:5432/postgres")
TENANT_NAME = os.getenv("TENANT_NAME", "Sentinela Ambiental")

# Bounding Box aproximado do Brasil para geração de dados fake
BRAZIL_LIMITS = {
    "lat": (-33.75, 5.27),
    "lon": (-73.99, -34.79)
}

# Struct de 32 bytes: Latitude (double), Longitude (double), Temperatura (double), Confiança (int), ID (int)
STRUCT_FORMAT = '=dddii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)

# Caminho do arquivo de metadados para comunicar SHM name ao processor
META_FILE = "/dev/shm/maas_shm_info.txt"

def get_or_create_tenant() -> str:
    """
    Busca ou cria o tenant no banco do MaaS.
    Retorna o tenant_id (UUID string).
    """
    print(f"[*] Auto-registro do tenant '{TENANT_NAME}' no banco MaaS...")
    
    retries = 10
    while retries > 0:
        try:
            conn = psycopg2.connect(MAAS_DB_URL)
            conn.autocommit = True
            with conn.cursor() as cur:
                # Busca no public (padrão MaaS Core)
                cur.execute(
                    "SELECT tenant_id FROM public.tenant WHERE name = %s LIMIT 1",
                    (TENANT_NAME,)
                )
                row = cur.fetchone()
                if row:
                    tenant_id = str(row[0])
                    print(f"[+] Tenant encontrado: {tenant_id}")
                    conn.close()
                    return tenant_id

                # Cria novo tenant (padrão Developer)
                cur.execute(
                    "INSERT INTO public.tenant (name, plan, status) VALUES (%s, 'Developer', 'active') RETURNING tenant_id",
                    (TENANT_NAME,)
                )
                tenant_id = str(cur.fetchone()[0])
                print(f"[+] Tenant criado: {TENANT_NAME} -> {tenant_id}")
                conn.close()
                return tenant_id
        except Exception as e:
            print(f"[-] Erro ao registrar tenant ({retries} tentativas restantes): {e}")
            retries -= 1
            time.sleep(3)

    raise RuntimeError("Falha ao registrar tenant no banco MaaS.")


def perform_maas_handshake(tenant_id: str) -> dict:
    """
    Realiza o handshake via gRPC com o serviço MaaS da Quilombus Network.
    Retorna dict com allocation_id, shm_key, offset.
    """
    print(f"[*] Iniciando Handshake gRPC com MaaS em {MAAS_GRPC_HOST}...")
    
    retries = 10
    while retries > 0:
        try:
            channel = grpc.insecure_channel(MAAS_GRPC_HOST)
            stub = maas_pb2_grpc.MemoryServiceStub(channel)
            
            request = maas_pb2.AllocateRequest(
                tenant_id=tenant_id,
                size_bytes=MAAS_BUFFER_SIZE
            )
            
            response = stub.Allocate(request, timeout=10)
            
            result = {
                "allocation_id": response.allocation_id,
                "shm_key": response.shm_key,
                "offset": response.offset,
            }
            
            print(f"[+] Handshake bem sucedido. Memória alocada via MaaS.")
            print(f"    allocation_id: {result['allocation_id']}")
            print(f"    shm_key:       {result['shm_key']}")
            print(f"    offset:        {result['offset']}")
            print(f"    size:          {MAAS_BUFFER_SIZE} bytes ({MAAS_BUFFER_SIZE / (1024*1024):.1f} MB)")
            
            # Salva metadados para o processor
            with open(META_FILE, "w") as f:
                f.write(f"{result['shm_key']}\n{result['allocation_id']}\n{MAAS_BUFFER_SIZE}\n")
            print(f"[+] Metadados salvos em {META_FILE}")
            
            return result
        except grpc.RpcError as e:
            print(f"[-] gRPC error ({e.code()}): {e.details()} — {retries} tentativas restantes")
            retries -= 1
            time.sleep(3)
        except Exception as e:
            print(f"[-] Erro no handshake MaaS: {e} — {retries} tentativas restantes")
            retries -= 1
            time.sleep(3)
    
    raise RuntimeError("Falha no Handshake MaaS após todas as tentativas.")


def get_active_region_bbox() -> str:
    default_bbox = "-41.87,-21.30,-39.66,-17.89"
    try:
        # Usa a conexão local da aplicação (onde o dashboard salva a config)
        conn = psycopg2.connect(DB_CONNECTION)
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM sentinela_ambiental.system_config WHERE key = 'active_region'")
            row = cur.fetchone()
            if row:
                sigla = row[0]
                return STATE_BBOX.get(sigla, STATE_BBOX.get('ES'))
    except Exception as e:
        print(f"[-] Erro ao ler config do BD local, usando fallback: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
    return default_bbox

def get_remote_memory(stub, allocation_id: str, size: int) -> MaaSMemory:
    """
    Inicializa a abstração de memória via rede.
    """
    print(f"[+] Inicializando acesso à memória via REDE (allocation_id: {allocation_id})")
    return MaaSMemory(stub, allocation_id, size)


def parse_confidence(conf_raw: str) -> int:
    """
    Normaliza os valores de confiança de satélites (ex: VIIRS retorna 'h', 'n', 'l').
    """
    if conf_raw.isdigit():
        return int(conf_raw)
    
    conf_raw = conf_raw.lower()
    if conf_raw == 'h': return 100
    if conf_raw == 'n': return 66
    if conf_raw == 'l': return 33
    return 0

def fetch_nasa_firms_data() -> list[dict]:
    """
    Consome a API FIRMS (NASA) para o BRASIL inteiro.
    Se a chave for padrão ou a API falhar, gera um dado fake nacional para validação.
    """
    data = []
    
    # Se a chave for a padrão, gera dado de teste imediatamente cobrindo o país
    if not NASA_MAP_KEY or "sua_chave" in NASA_MAP_KEY:
        import random
        return [{
            'id': int(time.time()), 
            'lat': random.uniform(BRAZIL_LIMITS['lat'][0], BRAZIL_LIMITS['lat'][1]), 
            'lon': random.uniform(BRAZIL_LIMITS['lon'][0], BRAZIL_LIMITS['lon'][1]), 
            'temp': random.uniform(330.0, 400.0), 
            'conf': random.randint(60, 100)
        } for _ in range(5)] # Gera 5 pontos espalhados

    # Endpoint de PAÍS (BRA = Brasil)
    url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{NASA_MAP_KEY}/VIIRS_SNPP_NRT/BRA/1"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            if len(lines) > 1:
                headers = lines[0].split(',')
                for idx, line in enumerate(lines[1:]):
                    values = line.split(',')
                    row = dict(zip(headers, values))
                    data.append({
                        'id': idx + 1,
                        'lat': float(row.get('latitude', 0.0)),
                        'lon': float(row.get('longitude', 0.0)),
                        'temp': float(row.get('brightness', 0.0)),
                        'conf': parse_confidence(row.get('confidence', '0'))
                    })
        
        # Fallback de teste caso a API retorne vazio para o Brasil todo
        if not data:
            print("[*] Nenhum foco real no Brasil agora. Gerando amostras nacionais de teste...")
            import random
            for _ in range(5):
                data.append({
                    'id': int(time.time()) + _, 
                    'lat': random.uniform(BRAZIL_LIMITS['lat'][0], BRAZIL_LIMITS['lat'][1]), 
                    'lon': random.uniform(BRAZIL_LIMITS['lon'][0], BRAZIL_LIMITS['lon'][1]), 
                    'temp': random.uniform(330.0, 420.0), 
                    'conf': random.randint(80, 100)
                })
            
        return data
    except Exception as exc:
        print(f"[-] Erro na API NASA Nacional: {exc}. Usando dados de contingência.")
        import random
        return [{'id': 999, 'lat': -15.0, 'lon': -47.0, 'temp': 350.0, 'conf': 100}]

def run_ingestor():
    # 1. Auto-registro do tenant no banco MaaS
    tenant_id = get_or_create_tenant()
    
    # 2. Handshake gRPC real com MaaS Core
    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)
    
    alloc = perform_maas_handshake(tenant_id)
    alloc_id = alloc["allocation_id"]
    
    # 3. Inicializa acesso à memória via rede
    mm = get_remote_memory(stub, alloc_id, MAAS_BUFFER_SIZE)
    
    offset = 0
    while True:
        try:
            firms_data = fetch_nasa_firms_data()
            print(f"[*] Ingerindo {len(firms_data)} registros no buffer MaaS...")
            
            for record in firms_data:
                # Controle do Buffer Circular (MaaS em RAM)
                if offset + RECORD_SIZE > MAAS_BUFFER_SIZE:
                    offset = 0
                    print("[*] Buffer MaaS cheio. Rebobinando ponteiro para 0 (Circular).")
                
                # Serialização Binária: dddii -> Lat, Lon, Temp, Conf, ID (32 bytes no total)
                packed_data = struct.pack(
                    STRUCT_FORMAT,
                    record['lat'],
                    record['lon'],
                    record['temp'],
                    record['conf'],
                    record['id']
                )
                
                mm.seek(offset)
                mm.write(packed_data)
                offset += RECORD_SIZE
                
            time.sleep(60) # Intervalo de polling. Ajustável conforme o Rate Limit da NASA.
            
        except Exception as e:
            print(f"[-] Falha detectada: {e}. O MaaS pode ter reiniciado.")
            time.sleep(5)
            try:
                # Tratamento de resiliência: Tentativa de re-conexão e re-alocação
                tenant_id = get_or_create_tenant()
                alloc = perform_maas_handshake(tenant_id)
                shm_name = alloc["shm_key"]
                mm = get_shared_memory(shm_name, MAAS_BUFFER_SIZE)
                offset = 0
            except Exception as e_retry:
                print(f"[-] Falha ao recuperar MaaS: {e_retry}")

if __name__ == "__main__":
    run_ingestor()
