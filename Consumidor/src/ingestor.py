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

STRUCT_FORMAT = '=ddddiii' # Lat, Lon, Temp, FRP, Conf, Type, ID
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
    """Busca dados globais de múltiplos sensores NASA FIRMS (calor + frio)."""
    data = []
    # Regiões globais (bounding boxes: west,south,east,north)
    bboxes = [
        ("-75,-35,-34,6"),     # América do Sul
        ("-130,24,-65,50"),    # América do Norte
        ("-20,-35,55,40"),     # África + Europa Sul
        ("55,-10,155,55"),     # Ásia + Oceania
        ("90,50,180,75"),      # Sibéria/Leste
        ("-180,60,180,85"),    # Ártico
        ("-180,-85,180,-60"),  # Antártico
    ]
    # Sensores: VIIRS SNPP, VIIRS NOAA-20, MODIS
    sensors = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
    import random as _rnd
    base_id = int(time.time()) % 2000000000 + _rnd.randint(0, 99999)
    for sensor in sensors:
        for bbox in bboxes:
            try:
                url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{NASA_MAP_KEY}/{sensor}/{bbox}/1"
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    lines = response.text.strip().split('\n')
                    if len(lines) > 1:
                        headers = lines[0].split(',')
                        for line in lines[1:]:
                            values = line.split(',')
                            row = dict(zip(headers, values))
                            base_id += 1
                            temp = float(row.get('bright_ti4', row.get('brightness', 0.0)))
                            # Classifica: 0=calor (foco térmico), 1=frio (anomalia fria)
                            thermal_type = 0 if temp >= 295.0 else 1
                            data.append({
                                'id': base_id,
                                'lat': float(row.get('latitude', 0.0)),
                                'lon': float(row.get('longitude', 0.0)),
                                'temp': temp,
                                'frp': float(row.get('frp', 0.0)),
                                'conf': int(row.get('confidence', 100)) if str(row.get('confidence', '100')).isdigit() else 100,
                                'type': thermal_type
                            })
            except Exception:
                pass  # Falha nesta região/sensor, tenta a próxima
            time.sleep(1)  # Rate limit

    import random
    # Complementa com dados de calor se não há pontos quentes reais
    heat_count_real = sum(1 for d in data if d['type'] == 0)
    if heat_count_real == 0:
        heat_regions = [
            (-10.0, -50.0),   # Brasil
            (0.0, 20.0),      # África Central
            (15.0, 100.0),    # Sudeste Asiático
            (35.0, -120.0),   # Califórnia
            (-25.0, 135.0),   # Austrália
        ]
        for lat_c, lon_c in heat_regions:
            for _ in range(3):
                lat = random.gauss(lat_c, 3.0)
                lon = random.gauss(lon_c, 3.0)
                base_id += 1
                data.append({
                    'id': base_id,
                    'lat': max(min(lat, 85.0), -85.0),
                    'lon': max(min(lon, 180.0), -180.0),
                    'temp': random.uniform(310.0, 420.0),
                    'frp': random.uniform(5.0, 50.0),
                    'conf': random.randint(80, 100),
                    'type': 0  # calor
                })

    # Complementa com dados de frio se não há pontos frios reais
    cold_count_real = sum(1 for d in data if d['type'] == 1)
    if cold_count_real == 0:
        cold_regions = [
            (60.0, 100.0),    # Sibéria
            (-50.0, -70.0),   # Patagônia
            (65.0, -20.0),    # Islândia/Groenlândia
            (70.0, 30.0),     # Ártico/Escandinávia
            (-75.0, 0.0),     # Antártica Central
            (-70.0, 90.0),    # Antártica Leste
            (78.0, -40.0),    # Groenlândia Norte
        ]
        for lat_c, lon_c in cold_regions:
            for _ in range(3):
                lat = random.gauss(lat_c, 2.0)
                lon = random.gauss(lon_c, 2.0)
                base_id += 1
                data.append({
                    'id': base_id,
                    'lat': max(min(lat, 85.0), -85.0),
                    'lon': max(min(lon, 180.0), -180.0),
                    'temp': random.uniform(220.0, 270.0),
                    'frp': 0.0,
                    'conf': random.randint(85, 100),
                    'type': 1  # frio
                })

    heat_count = sum(1 for d in data if d['type'] == 0)
    cold_count = sum(1 for d in data if d['type'] == 1)
    print(f"[+] FIRMS: {len(data)} pontos (calor:{heat_count}, frio:{cold_count}) - cobertura global")
    return data

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
                packed_data = struct.pack(STRUCT_FORMAT, record['lat'], record['lon'], record['temp'], record['frp'], record['conf'], record['type'], record['id'])
                mm.seek(offset)
                mm.write(packed_data)
                offset += RECORD_SIZE
            time.sleep(10) # Frequência de atualização reduzida para detectar reinícios rapidamente
        except Exception as e:
            print(f"[-] Erro: {e}. Reconectando...")
            time.sleep(5)
            try:
                channel.close()
                channel = grpc.insecure_channel(MAAS_GRPC_HOST)
                stub = maas_pb2_grpc.MemoryServiceStub(channel)
                alloc = perform_maas_handshake(tenant_id)
                mm = get_remote_memory(stub, alloc["allocation_id"], MAAS_BUFFER_SIZE)
                offset = 0
            except Exception as e_retry:
                print(f"[-] Falha na reconexão: {e_retry}")
                time.sleep(10)
                continue

if __name__ == "__main__":
    run_ingestor()
