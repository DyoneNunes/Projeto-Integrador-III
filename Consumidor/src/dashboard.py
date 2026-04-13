import os
import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import requests
import struct
import grpc
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Importa stubs gRPC
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc
from maas_client import MaaSMemory

# 1. CONFIGURAÇÃO DA PÁGINA E ESTILO
st.set_page_config(
    page_title="Sentinela Ambiental",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS customizado para o tema "Sentinela"
st.markdown("""
    <style>
    .stMetric { padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    </style>
    """, unsafe_allow_html=True)

# 2. CARREGAMENTO DE AMBIENTE E CONEXÃO
DB_CONNECTION = os.getenv("DB_CONNECTION")

@st.cache_resource
def get_engine():
    """Retorna o engine de conexão com o banco via SQLAlchemy."""
    return create_engine(DB_CONNECTION)

# 2.2 INTEGRAÇÃO MAAS (MODO REDE GRP)
STRUCT_FORMAT = '=dddii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)
META_FILE = "/dev/shm/maas_shm_info.txt"
MAAS_GRPC_HOST = os.getenv("MAAS_GRPC_HOST", "100.114.106.28:50051")

@st.cache_resource
def get_maas_stub():
    channel = grpc.insecure_channel(MAAS_GRPC_HOST)
    return maas_pb2_grpc.MemoryServiceStub(channel)

@st.cache_data(ttl=30)
def get_maas_live_data() -> pd.DataFrame:
    """
    Lê os dados de tempo real via Rede (gRPC) da RAM alocada via MaaS.
    """
    if not os.path.exists(META_FILE):
        return pd.DataFrame()
    
    try:
        with open(META_FILE, "r") as f:
            lines = f.read().strip().split("\n")
        if len(lines) < 3: return pd.DataFrame()
        
        alloc_id = lines[1]
        size = int(lines[2])
        
        stub = get_maas_stub()
        mm = MaaSMemory(stub, alloc_id, size)
        
        data = []
        # Lemos os últimos 500 registros para o Live Map
        total_records = size // RECORD_SIZE
        records_to_read = min(500, total_records)
        
        for i in range(records_to_read):
            mm.seek(i * RECORD_SIZE)
            chunk = mm.read(RECORD_SIZE)
            if not chunk or chunk == b'\x00' * RECORD_SIZE:
                continue
            
            lat, lon, temp_k, conf, rec_id = struct.unpack(STRUCT_FORMAT, chunk)
            if rec_id == 0: continue
            
            data.append({
                'latitude': lat,
                'longitude': lon,
                'temperature_k': temp_k,
                'temperature_c': temp_k - 273.15,
                'confidence': conf,
                'reading_timestamp': datetime.now().replace(microsecond=0),
                'alert_type': 'LIVE_MaaS_Network',
                'severity': 'CRITICAL' if temp_k > 330 else 'INFO'
            })
            
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

def get_data(hours: int) -> pd.DataFrame:
    """Busca dados processados do PostgreSQL dentro da janela de tempo."""
    engine = get_engine()
    query = f"""
        SELECT 
            sr.latitude, sr.longitude, sr.temperature_k, sr.confidence, sr.reading_timestamp,
            ah.alert_type, ah.severity
        FROM sentinela_ambiental.sensor_readings sr
        JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
        WHERE sr.reading_timestamp >= NOW() - INTERVAL '{hours} hours'
        ORDER BY sr.reading_timestamp DESC
    """
    try:
        df = pd.read_sql(query, engine)
        df['temperature_c'] = df['temperature_k'] - 273.15
        return df
    except Exception:
        return pd.DataFrame()

# 3. SIDEBAR E INTEGRAÇÃO IBGE
@st.cache_data(ttl=3600)
def get_ibge_states():
    try:
        response = requests.get("https://servicodados.ibge.gov.br/api/v1/localidades/estados", timeout=5)
        if response.status_code == 200:
            states = response.json()
            states = sorted(states, key=lambda x: x["nome"])
            result = {"Brasil (Todo o País)": "BR"}
            for s in states:
                result[f"{s['nome']} ({s['sigla']})"] = s['sigla']
            return result
    except Exception: pass
    return {"Brasil": "BR", "Espírito Santo (ES)": "ES"}

def set_active_region(sigla: str):
    engine = get_engine()
    query_upsert = text("""
        INSERT INTO sentinela_ambiental.system_config (key, value) 
        VALUES ('active_region', :val)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
    """)
    try:
        with engine.begin() as conn:
            conn.execute(query_upsert, {"val": sigla})
    except Exception: pass

STATE_BBOX = {
    'AC': [-73.99, -11.14, -66.62, -7.11], 'AL': [-38.23, -10.50, -35.15, -8.81],
    'AP': [-54.87, -1.23, -49.88, 4.44], 'AM': [-73.80, -9.81, -56.09, 2.24],
    'BA': [-46.61, -18.34, -37.34, -8.53], 'CE': [-41.41, -7.85, -37.25, -2.78],
    'DF': [-48.28, -16.05, -47.30, -15.50], 'ES': [-41.87, -21.30, -39.66, -17.89],
    'GO': [-53.25, -19.49, -45.90, -12.39], 'MA': [-48.74, -10.26, -41.79, -1.05],
    'MT': [-61.64, -18.04, -50.22, -6.14], 'MS': [-58.16, -24.06, -50.92, -17.15],
    'MG': [-51.04, -22.92, -39.85, -14.23], 'PA': [-58.89, -9.85, -46.06, 2.59],
    'PB': [-38.76, -8.30, -34.79, -6.02], 'PR': [-54.61, -26.71, -48.02, -22.51],
    'PE': [-41.35, -9.48, -34.79, -7.04], 'PI': [-45.92, -10.92, -40.37, -2.74],
    'RJ': [-44.88, -23.36, -40.96, -20.76], 'RN': [-38.58, -6.98, -34.97, -4.83],
    'RS': [-57.64, -33.75, -49.69, -27.08], 'RO': [-66.80, -13.69, -59.77, -7.96],
    'RR': [-64.82, -1.58, -58.88, 5.27], 'SC': [-53.83, -29.35, -48.33, -25.95],
    'SP': [-53.11, -25.31, -44.16, -19.77], 'SE': [-38.24, -11.56, -36.39, -9.51],
    'TO': [-50.74, -13.47, -45.53, -5.16]
}

st.sidebar.title("Configurações")
st.sidebar.markdown("---")

hours_filter = st.sidebar.slider("Janela de Tempo (Horas)", 1, 72, 24)

st.sidebar.markdown("### 📍 Região de Análise")
ibge_states = get_ibge_states()
state = st.sidebar.selectbox("Estado", list(ibge_states.keys()))
state_sigla = ibge_states[state]

# Controle de estado para evitar gravações constantes
if 'last_state' not in st.session_state:
    st.session_state.last_state = state_sigla
    set_active_region(state_sigla)

if st.session_state.last_state != state_sigla:
    st.session_state.last_state = state_sigla
    set_active_region(state_sigla)
    st.rerun()

st.sidebar.info(f"Monitorando: {state}, Brasil")
st.sidebar.markdown("---")
st.sidebar.caption("Powered by **Quilombus MaaS** & **NASA FIRMS**")

# 4. DASHBOARD PRINCIPAL
st.title("🛡️ Sentinela Ambiental")
st.subheader(f"Monitoramento Térmico - {state} (Tempo Real via MaaS)")

df_history = get_data(hours_filter)
df_live = get_maas_live_data()

if not df_live.empty:
    st.sidebar.success("⚡ Conectado ao MaaS RAM (Network)")
    df_alerts = pd.concat([df_live, df_history]).drop_duplicates(subset=['latitude', 'longitude'], keep='first')
else:
    st.sidebar.warning("⏳ Aguardando MaaS Remote...")
    df_alerts = df_history

# FILTRAGEM ESPACIAL
if state_sigla == "BR":
    map_center, map_zoom = [-14.235, -51.9253], 4
else:
    bbox = STATE_BBOX.get(state_sigla, STATE_BBOX['ES'])
    map_center, map_zoom = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2], 6
    df_alerts = df_alerts[
        (df_alerts['latitude'] >= bbox[1]) & (df_alerts['latitude'] <= bbox[3]) &
        (df_alerts['longitude'] >= bbox[0]) & (df_alerts['longitude'] <= bbox[2])
    ]

if df_alerts.empty:
    st.warning(f"⚠️ Nenhum alerta detectado em {state}.")
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="cartodbpositron")
    st_folium(m, width="100%", height=500, key="maas_map")
else:
    # KPIS
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas Críticos", len(df_alerts))
    c2.metric("Nível de Crise", "Crítica" if len(df_alerts) > 100 else "Atenção" if len(df_alerts) > 20 else "Leve")
    c3.metric("Pico Identificado", f"{df_alerts['temperature_c'].max():.1f} °C")
    c4.metric("Status MaaS", "Connected")

    # MAPA
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="cartodbpositron")
    for _, row in df_alerts.iterrows():
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=row['confidence'] / 10,
            color="red" if row['temperature_c'] > 60 else "orange",
            fill=True, fill_opacity=0.7,
            tooltip=f"{row['temperature_c']:.1f} °C 🔥"
        ).add_to(m)
    st_folium(m, width="100%", height=500, key="maas_map")

st.markdown("---")
st.caption(f"Dados atualizados em: {datetime.now().strftime('%H:%M:%S')} | Modo de Rede Direto Ativado")
