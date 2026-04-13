import os
import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import requests
import mmap
import posix_ipc
import struct
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

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
    /* Removendo background-color fixo para respeitar o tema Claro/Escuro do Streamlit */
    .stMetric { padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    </style>
    """, unsafe_allow_html=True)

# 2. CARREGAMENTO DE AMBIENTE E CONEXÃO
load_dotenv()

DB_CONNECTION = os.getenv("DB_CONNECTION")

@st.cache_resource
def get_engine():
    """Retorna o engine de conexão com o banco via SQLAlchemy."""
    return create_engine(DB_CONNECTION)

# 2.2 INTEGRAÇÃO MAAS (SISTEMA DE MEMÓRIA GERENCIADA)
STRUCT_FORMAT = '=dddii'
RECORD_SIZE = struct.calcsize(STRUCT_FORMAT)
META_FILE = "/dev/shm/maas_shm_info.txt"

@st.cache_data(ttl=30)
def get_maas_live_data() -> pd.DataFrame:
    """
    Lê os dados de tempo real diretamente da RAM alocada via MaaS.
    Isso economiza recursos do servidor local (Stateless Client).
    """
    if not os.path.exists(META_FILE):
        return pd.DataFrame()
    
    try:
        with open(META_FILE, "r") as f:
            lines = f.read().strip().split("\n")
        if len(lines) < 3: return pd.DataFrame()
        
        shm_name = lines[0]
        size = int(lines[2])
        
        memory = posix_ipc.SharedMemory(shm_name)
        with mmap.mmap(memory.fd, memory.size, access=mmap.ACCESS_READ) as mm:
            data = []
            # Lemos apenas os últimos 500 registros para otimizar a renderização do mapa
            # O buffer circular pode ter milhares, mas para visualização 'Live' focamos no topo
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
                    'reading_timestamp': datetime.now().replace(microsecond=0), # Estabiliza o timestamp para o cache
                    'alert_type': 'LIVE_MaaS',
                    'severity': 'CRITICAL' if temp_k > 330 else 'INFO'
                })
            
            memory.close_fd()
            return pd.DataFrame(data)
    except Exception as e:
        # Silencioso no dash para não poluir UI se o MaaS ainda estiver subindo
        return pd.DataFrame()

def get_data(hours: int) -> pd.DataFrame:
    """Busca dados processados do PostgreSQL dentro da janela de tempo."""
    engine = get_engine()
    query = f"""
        SELECT 
            sr.latitude, 
            sr.longitude, 
            sr.temperature_k, 
            sr.confidence, 
            sr.reading_timestamp,
            ah.alert_type,
            ah.severity
        FROM sentinela_ambiental.sensor_readings sr
        JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
        WHERE sr.reading_timestamp >= NOW() - INTERVAL '{hours} hours'
        ORDER BY sr.reading_timestamp DESC
    """
    try:
        df = pd.read_sql(query, engine)
        # Conversão de Kelvin para Celsius para melhor leitura humana
        df['temperature_c'] = df['temperature_k'] - 273.15
        return df
    except Exception as e:
        st.error(f"Erro ao conectar ao Banco de Dados: {e}")
        return pd.DataFrame()

# 3. SIDEBAR E INTEGRAÇÃO IBGE
@st.cache_data
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
    except Exception as e:
        st.error(f"Erro ao buscar estados do IBGE: {e}")
    return {"Brasil": "BR", "Espírito Santo (ES)": "ES"} # Fallback

def set_active_region(sigla: str):
    engine = get_engine()
    query_create = text("""
        CREATE TABLE IF NOT EXISTS sentinela_ambiental.system_config (
            key VARCHAR(50) PRIMARY KEY,
            value VARCHAR(255) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    query_upsert = text("""
        INSERT INTO sentinela_ambiental.system_config (key, value) 
        VALUES ('active_region', :val)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
    """)
    try:
        with engine.begin() as conn:
            conn.execute(query_create)
            conn.execute(query_upsert, {"val": sigla})
    except Exception as e:
        st.error(f"Erro ao salvar região ativa: {e}")

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

hours_filter = st.sidebar.slider(
    "Janela de Tempo (Horas)",
    min_value=1,
    max_value=72,
    value=24,
    help="Selecione o período retroativo para visualização dos focos de calor."
)

st.sidebar.markdown("### 📍 Região de Análise")

country = st.sidebar.selectbox("País", ["Brasil"])

ibge_states = get_ibge_states()
state_options = list(ibge_states.keys())
state = st.sidebar.selectbox("Estado", state_options)
state_sigla = ibge_states[state]

st.sidebar.info(f"Monitorando: {state}, {country}")

# 3.2 CONTROLE DE ESTADO (EVITA RERUNS INFINITOS)
if 'last_state' not in st.session_state:
    st.session_state.last_state = state_sigla
    set_active_region(state_sigla)

if st.session_state.last_state != state_sigla:
    st.session_state.last_state = state_sigla
    set_active_region(state_sigla)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Powered by **Quilombus MaaS** & **NASA FIRMS**")

# 4. DASHBOARD PRINCIPAL
st.title("🛡️ Sentinela Ambiental")
st.subheader(f"Monitoramento Térmico - {state} em Tempo Real")

st.markdown(f"Visualizando dados das últimas **{hours_filter} horas** processados via Memory-as-a-Service.")

# Busca de dados de histórico (Banco de Dados)
df_history = get_data(hours_filter)

# Busca de dados em Tempo Real (Direto da RAM MaaS)
df_live = get_maas_live_data()

# Merge dos dados priorizando o "Live"
if not df_live.empty:
    st.sidebar.success("⚡ Conectado ao MaaS RAM (Live)")
    # Concatena live com histórico
    df_alerts = pd.concat([df_live, df_history]).drop_duplicates(subset=['latitude', 'longitude'], keep='first')
else:
    st.sidebar.warning("⏳ MaaS RAM Offline (Usando apenas histórico)")
    df_alerts = df_history

# LÓGICA DE FILTRAGEM ESPACIAL
if state_sigla == "BR":
    map_center = [-14.235, -51.9253]
    map_zoom = 4
else:
    bbox = STATE_BBOX.get(state_sigla, STATE_BBOX['ES'])
    map_center = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]
    map_zoom = 6

    # Filtra o DataFrame espacialmente pela bounding box do estado
    df_alerts = df_alerts[
        (df_alerts['latitude'] >= bbox[1]) &
        (df_alerts['latitude'] <= bbox[3]) &
        (df_alerts['longitude'] >= bbox[0]) &
        (df_alerts['longitude'] <= bbox[2])
    ]

if df_alerts.empty:
    st.warning(f"⚠️ Nenhum alerta crítico detectado em {state} para o período selecionado.")
    # Mesmo sem dados, mostra o mapa centralizado no Estado
    st.markdown("### 🗺️ Mapa de Anomalias Térmicas")
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="cartodbpositron")
    st_folium(m, width="100%", height=500)

else:
    # 5. KPIS / MÉTRICAS DE IMPACTO
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Alertas Críticos", len(df_alerts), delta=f"+{len(df_alerts[df_alerts['reading_timestamp'] > (datetime.now() - timedelta(hours=1))])} na última hora")
    
    with col2:
        # Puxa o clima REAL da região selecionada para contexto
        import requests
        def get_weather(lat, lon):
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    return r.json().get("current_weather", {}).get("temperature")
            except: pass
            return None
        
        real_temp = get_weather(map_center[0], map_center[1])
        if real_temp:
            st.metric("Temp. Ambiente Atual", f"{real_temp} °C", help="Temperatura climática real medida agora na cidade.")
        else:
            st.metric("Temp. Ambiente Atual", "-- °C")
        
    with col3:
        st.metric("Nível de Crise", "Crítica" if len(df_alerts) > 100 else "Atenção" if len(df_alerts) > 20 else "Leve")
        
    with col4:
        # Mostra o pico de temperatura do Estado selecionado
        if len(df_alerts) > 0:
            max_temp = df_alerts['temperature_c'].max()
            st.metric("Pico de Temp. Identificada", f"{max_temp:.1f} °C")
        else:
            st.metric("Pico de Temp.", "--")

    # 6. MAPA INTERATIVO (FOLIUM)
    st.markdown("### 🗺️ Mapa de Anomalias Térmicas")
    
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="cartodbpositron")
    
    for _, row in df_alerts.iterrows():
        # Cor baseada na severidade/temperatura
        color = "red" if row['temperature_c'] > 60 else "orange"
        
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=row['confidence'] / 10, # Tamanho baseado na confiança
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=f"Foco a {row['temperature_c']:.1f} °C 🔥",
            popup=folium.Popup(f"""
                <b>🔥 ALERTA DE INCÊNDIO / CALOR</b><br>
                <b>Tipo:</b> {row['alert_type']}<br>
                <b>Temp do Foco (Solo):</b> <span style="color:red">{row['temperature_c']:.2f} °C</span><br>
                <b>Confiança:</b> {row['confidence']}%<br>
                <b>Horário:</b> {row['reading_timestamp'].strftime('%H:%M:%S')}
            """, max_width=250)
        ).add_to(m)

    st_folium(m, width="100%", height=500, key="maas_map")

    # 7. ANÁLISE TEMPORAL E TABELA
    c_left, c_right = st.columns([2, 1])
    
    with c_left:
        st.markdown("### 📈 Tendência de Calor (Frequência)")
        df_alerts['hora'] = df_alerts['reading_timestamp'].dt.hour
        fig = px.histogram(df_alerts, x="hora", nbins=24, 
                           title="Distribuição de Alertas por Hora do Dia",
                           labels={'hora': 'Hora do Dia', 'count': 'Nº de Alertas'},
                           color_discrete_sequence=['#e63946'])
        st.plotly_chart(fig, use_container_width=True)

    with c_right:
        st.markdown("### 📋 Últimos Registros")
        st.dataframe(
            df_alerts[['temperature_c', 'confidence', 'reading_timestamp']].head(10),
            use_container_width=True
        )

# Rodapé técnico
st.markdown("---")
st.caption(f"Dados atualizados em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Filtragem Espacial Dinâmica Ativada")
