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
MAAS_BUFFER_SIZE = int(os.getenv("MAAS_BUFFER_SIZE", 104857600))
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "100.114.106.28:50051")
MAAS_DB_URL = os.getenv("MAAS_DB_URL")
DB_CONNECTION = os.getenv("DB_CONNECTION")
TENANT_NAME = os.getenv("TENANT_NAME", "Sentinela Ambiental")

BRAZIL_LIMITS = {"lat": (-33.75, 5.27), "lon": (-73.99, -34.79)}
STRUCT_FORMAT = '=dddii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)
META_FILE = "/dev/shm/maas_shm_info.txt"

def get_or_create_tenant() -> str:
    print(f"[*] Auto-registro do tenant '{TENANT_NAME}' no banco MaaS...")
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
    raise RuntimeError("Falha ao registrar tenant no banco MaaS.")

def perform_maas_handshake(tenant_id: str) -> dict:
    print(f"[*] Iniciando Handshake gRPC com MaaS em {MAAS_GRPC_HOST}...")
    retries = 10
    while retries > 0:
        try:
            channel = grpc.insecure_channel(MAAS_GRPC_HOST)
            stub = maas_pb2_grpc.MemoryServiceStub(channel)
            request = maas_pb2.AllocateRequest(tenant_id=tenant_id, size_bytes=MAAS_BUFFER_SIZE)
            response = stub.Allocate(request, timeout=10)
            result = {"allocation_id": response.allocation_id, "shm_key": response.shm_key, "offset": response.offset}
            with open(META_FILE, "w") as f:
                f.write(f"{result['shm_key']}\n{result['allocation_id']}\n{MAAS_BUFFER_SIZE}\n")
            return result
        except Exception as e:
            retries -= 1
            time.sleep(3)
    raise RuntimeError("Falha no Handshake MaaS.")

def get_remote_memory(stub, allocation_id: str, size: int) -> MaaSMemory:
    print(f"[+] Inicializando acesso à memória via REDE (allocation_id: {allocation_id})")
    return MaaSMemory(stub, allocation_id, size)

def fetch_nasa_firms_data() -> list[dict]:
    data = []
    if not NASA_MAP_KEY or "sua_chave" in NASA_MAP_KEY:
        import random
        return [{'id': int(time.time()), 'lat': random.uniform(BRAZIL_LIMITS['lat'][0], BRAZIL_LIMITS['lat'][1]), 'lon': random.uniform(BRAZIL_LIMITS['lon'][0], BRAZIL_LIMITS['lon'][1]), 'temp': random.uniform(330.0, 400.0), 'conf': random.randint(60, 100)} for _ in range(5)]
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
                    data.append({'id': idx + 1, 'lat': float(row.get('latitude', 0.0)), 'lon': float(row.get('longitude', 0.0)), 'temp': float(row.get('brightness', 0.0)), 'conf': 100})
        if not data:
            import random
            for _ in range(5):
                data.append({'id': int(time.time()) + _, 'lat': random.uniform(BRAZIL_LIMITS['lat'][0], BRAZIL_LIMITS['lat'][1]), 'lon': random.uniform(BRAZIL_LIMITS['lon'][0], BRAZIL_LIMITS['lon'][1]), 'temp': random.uniform(330.0, 420.0), 'conf': random.randint(80, 100)})
        return data
    except Exception:
        return [{'id': 999, 'lat': -15.0, 'lon': -47.0, 'temp': 350.0, 'conf': 100}]

def run_ingestor():
    tenant_id = get_or_create_tenant()
    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)
    alloc = perform_maas_handshake(tenant_id)
    mm = get_remote_memory(stub, alloc["allocation_id"], MAAS_BUFFER_SIZE)
    offset = 0
    while True:
        try:
            firms_data = fetch_nasa_firms_data()
            for record in firms_data:
                if offset + RECORD_SIZE > MAAS_BUFFER_SIZE:
                    offset = 0
                packed_data = struct.pack(STRUCT_FORMAT, record['lat'], record['lon'], record['temp'], 100, record['id'])
                mm.seek(offset)
                mm.write(packed_data)
                offset += RECORD_SIZE
            time.sleep(60)
        except Exception as e:
            print(f"[-] Erro: {e}. Reconectando...")
            time.sleep(5)
            try:
                alloc = perform_maas_handshake(tenant_id)
                mm = get_remote_memory(stub, alloc["allocation_id"], MAAS_BUFFER_SIZE)
                offset = 0
            except: pass

if __name__ == "__main__":
    run_ingestor()
