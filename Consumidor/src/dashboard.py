import os
import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
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

# 2.2 INTEGRAÇÃO MAAS (MODO REDE GRP) - PROTOCOLO 44 BYTES
STRUCT_FORMAT = '=ddddiii'
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
            
            lat, lon, temp_k, frp, conf, sat_type, rec_id = struct.unpack(STRUCT_FORMAT, chunk)
            if rec_id == 0: continue
            
            data.append({
                'latitude': lat,
                'longitude': lon,
                'temperature_k': temp_k,
                'temperature_c': temp_k - 273.15,
                'frp': frp,
                'confidence': conf,
                'satellite_type': sat_type,
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
    query = text("""
        SELECT 
            sr.latitude, sr.longitude, sr.temperature_k, sr.frp, sr.confidence, sr.reading_timestamp,
            ah.alert_type, ah.severity
        FROM sentinela_ambiental.sensor_readings sr
        JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
        WHERE sr.reading_timestamp >= NOW() - CAST(:hours || ' hours' AS INTERVAL)
        ORDER BY sr.reading_timestamp DESC
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"hours": hours})
        df['temperature_c'] = df['temperature_k'] - 273.15
        return df
    except Exception as e:
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

def get_weather(lat, lon):
    """Puxa o clima REAL da região para contexto analítico."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            return r.json().get("current_weather", {}).get("temperature")
    except: pass
    return None

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

# 📍 Configurações de Filtro
hours_filter = st.sidebar.slider("Janela de Tempo (Horas)", 1, 72, 24)

st.sidebar.markdown("### 🔭 Modo de Análise")
analysis_mode = st.sidebar.radio(
    "Selecione o tipo de dados:",
    ["🔥 Mapa de Calor (Anomalias)", "❄️ Mapa de Frio (Ambiente)"],
    help="Alterne entre visualização de focos de incêndio e temperaturas ambiente estáveis."
)

st.sidebar.markdown("### 🎨 Aparência do Mapa")
hm_radius = st.sidebar.slider("Raio do Calor", 5, 50, 15)
hm_blur = st.sidebar.slider("Efeito de Desfoque", 1, 30, 10)

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
st.subheader(f"Monitoramento Térmico - {state} ({'Focos de Calor' if 'Calor' in analysis_mode else 'Zonas de Resfriamento'})")

df_history = get_data(hours_filter)
df_live = get_maas_live_data()

# Mesclagem e Filtro por Modo de Análise
if not df_live.empty:
    st.sidebar.success("⚡ Conectado ao MaaS RAM (Network)")
    df_all = pd.concat([df_live, df_history]).drop_duplicates(subset=['latitude', 'longitude'], keep='first')
else:
    st.sidebar.warning("⏳ Aguardando MaaS Remote...")
    df_all = df_history

# FILTRAGEM POR MODO (Calor: >= 57°C / Frio: < 57°C)
THRESHOLD_C = 57.0
if "Calor" in analysis_mode:
    df_alerts = df_all[df_all['temperature_c'] >= THRESHOLD_C].copy()
    main_color = "#e63946" # Vermelho
    color_scale = "Reds"
    hm_gradient = {0.4: 'yellow', 0.65: 'orange', 1: 'red'}
else:
    df_alerts = df_all[df_all['temperature_c'] < THRESHOLD_C].copy()
    main_color = "#00b4d8" # Azul Cyan
    color_scale = "Blues"
    hm_gradient = {0.4: 'cyan', 0.65: 'blue', 1: 'darkblue'}

# FILTRAGEM ESPACIAL
if state_sigla == "BR":
    map_center, map_zoom = [-14.235, -51.9253], 4
else:
    bbox = STATE_BBOX.get(state_sigla, STATE_BBOX['ES'])
    map_center, map_zoom = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2], 6
    if not df_alerts.empty:
        df_alerts = df_alerts[
            (df_alerts['latitude'] >= bbox[1]) & (df_alerts['latitude'] <= bbox[3]) &
            (df_alerts['longitude'] >= bbox[0]) & (df_alerts['longitude'] <= bbox[2])
        ]

# SANITIZAÇÃO DE DADOS (protege contra registros corrompidos no banco)
# Limites físicos reais do sensor VIIRS:
#   - FRP: 0 a ~5000 MW (incêndios extremos raramente passam de 2000 MW)
#   - Brightness Temp: 200 a 1000 K (faixa do canal I-4 / I-5)
#   - Confidence: 0 a 100 (%)
if not df_alerts.empty:
    df_alerts = df_alerts[
        (df_alerts['temperature_k'] >= 200) & (df_alerts['temperature_k'] <= 1000)
    ].copy()
    df_alerts['confidence'] = df_alerts['confidence'].clip(lower=0, upper=100)
    if 'frp' in df_alerts.columns:
        df_alerts = df_alerts[df_alerts['frp'] <= 5000].copy()
        df_alerts['frp'] = df_alerts['frp'].clip(lower=0)
    df_alerts['temperature_c'] = df_alerts['temperature_k'] - 273.15

if df_alerts.empty:
    st.warning(f"⚠️ Nenhum registro detectado nesta categoria em {state}.")
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="cartodbpositron")
    st_folium(m, width="100%", height=500, key="maas_map_empty")
else:
    # 5. KPIS / MÉTRICAS DE IMPACTO
    c1, c2, c3, c4 = st.columns(4)
    
    # Delta de última hora
    last_hour_count = len(df_alerts[df_alerts['reading_timestamp'] > (datetime.now() - timedelta(hours=1))])
    
    label_alertas = "Focos Ativos" if "Calor" in analysis_mode else "Pontos Estáveis"
    c1.metric(label_alertas, len(df_alerts), delta=f"{last_hour_count} na última hora")
    
    # Clima Real
    real_temp = get_weather(map_center[0], map_center[1])
    if real_temp:
        c2.metric("Temp. Ambiente", f"{real_temp} °C", help="Temperatura climática real medida agora na região.")
    else:
        c2.metric("Temp. Ambiente", "-- °C")
        
    if "Calor" in analysis_mode:
        label_pico = "Pico Radiativo (FRP)"
        if 'frp' in df_alerts.columns and df_alerts['frp'].notna().any() and df_alerts['frp'].max() > 0:
            val_pico = df_alerts['frp'].max()
            c3.metric(label_pico, f"{val_pico:.1f} MW", help="Fire Radiative Power — potência real do foco de incêndio medida pelo satélite.")
        else:
            c3.metric(label_pico, "-- MW", help="FRP indisponível neste lote de dados.")
    else:
        val_pico = df_alerts['temperature_c'].min()
        c3.metric("Mínima Registrada", f"{val_pico:.1f} °C")
    
    c4.metric("Confiança Média", f"{df_alerts['confidence'].mean():.1f}%")

    # 6. MAPA INTERATIVO (HEATMAP + FOCUS MARKERS + NASA GIBS)
    st.markdown(f"### 🗺️ {'Mapa de Anomalias Térmicas' if 'Calor' in analysis_mode else 'Mapa de Estabilidade Térmica'}")
    
    # Cálculo de Data para NASA GIBS (Imagens de Satélite de 24h atrás para garantir disponibilidade)
    gibs_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    m = folium.Map(location=map_center, zoom_start=map_zoom, tiles=None)

    # 1. CAMADAS DE FUNDO (TILE LAYERS)
    folium.TileLayer(
        tiles="cartodbpositron",
        name="🗺️ Cartográfico (Claro)",
        control=True
    ).add_to(m)

    # 🛰️ SATÉLITE DE ALTA FIDELIDADE (ESRI - SEM LISTRAS)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community",
        name="🛰️ Satélite Seamless (Alta Resolução)",
        overlay=False,
        control=True
    ).add_to(m)

    # 2. CAMADAS DE SOBREPOSIÇÃO (OVERLAYS)
    # NASA GIBS: Thermal Anomalies (Pontos Oficiais da NASA para comparação)
    gibs_thermal_url = (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        "VIIRS_SNPP_Thermal_Anomalies_375m_Night/default/"
        f"{gibs_date}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.png"
    )
    folium.TileLayer(
        tiles=gibs_thermal_url,
        attr="NASA EOSDIS GIBS",
        name="🛰️ Focos Oficiais NASA (Overlay)",
        overlay=True,
        control=True,
        show=False 
    ).add_to(m)

    # 3. NOSSO MOTOR DE MAPA DE CALOR (INTERPOLADO)
    heat_data = [
        [row['latitude'], row['longitude'], (row['temperature_c'] * (row['confidence']/100))] 
        for _, row in df_alerts.iterrows()
    ]
    
    dynamic_radius = hm_radius if state_sigla != "BR" else (hm_radius * 0.7)
    
    # Gradiente Profissional: Começa com opacidade 0 para evitar o efeito "quadrado"
    prof_gradient = {0.0: 'transparent', 0.2: 'blue' if 'Frio' in analysis_mode else 'yellow', 0.4: 'cyan' if 'Frio' in analysis_mode else 'orange', 0.7: 'blue' if 'Frio' in analysis_mode else 'red', 1.0: 'darkblue' if 'Frio' in analysis_mode else 'darkred'}

    HeatMap(
        heat_data, 
        name="🔥 Nosso Motor Térmico (MaaS)",
        radius=dynamic_radius, 
        blur=hm_blur, 
        gradient=prof_gradient, 
        min_opacity=0.0, # IMPORTANTE: Começa do zero absoluto para suavidade total
        control=True
    ).add_to(m)
    
    # 4. MARCADORES DE FOCO (TOP 10)
    if "Calor" in analysis_mode and 'frp' in df_alerts.columns:
        top_extremes = df_alerts.sort_values('frp', ascending=False).head(10)
    else:
        top_extremes = df_alerts.sort_values('temperature_c', ascending=("Calor" in analysis_mode)).head(10)
    
    for _, row in top_extremes.iterrows():
        frp_val = row.get('frp', 0) or 0
        tooltip_text = f"FRP: {frp_val:.1f} MW" if frp_val > 0 else f"BT: {row['temperature_c']:.1f} °C"
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=9,
            color=main_color,
            fill=True,
            fill_opacity=1.0,
            weight=3,
            tooltip=f"{tooltip_text} (Pico de Interesse)",
            popup=folium.Popup(f"""
                <div style="font-family: Arial; width: 240px;">
                    <h4 style="margin:0; color:{main_color}; font-weight: bold;">📍 FOCO PRIORITÁRIO</h4>
                    <hr style="margin:5px 0; border: 1px solid {main_color};">
                    <b>FRP (Potência):</b> {frp_val:.2f} MW<br>
                    <b>Confiança:</b> <span style="color:green;">{row['confidence']}%</span><br>
                    <b>Horário:</b> {row['reading_timestamp'].strftime('%H:%M:%S')}<br>
                    <b>Categoria:</b> {row['alert_type']}<br>
                    <hr style="margin:5px 0; border: 1px dashed #ccc;">
                    <small style="color:#888;">📡 Brightness Temp: {row['temperature_k']:.1f} K ({row['temperature_c']:.1f} °C)<br>
                    <em>Nota: BT é radiometria, não temp. ambiente.</em></small>
                </div>
            """, max_width=260)
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    
    st_folium(m, width="100%", height=600, key=f"maas_map_{analysis_mode}_{state_sigla}")

    st.markdown("---")
    
    # 7. ANÁLISE DE DADOS (GRÁFICOS)
    st.markdown("### 📈 Painel Analítico")
    col_left, col_right = st.columns(2)
    
    with col_left:
        # Tendência Temporal
        df_alerts['hora'] = df_alerts['reading_timestamp'].dt.hour
        fig_hist = px.histogram(
            df_alerts, x="hora", nbins=24, 
            title=f"Frequência por Hora ({'Calor' if 'Calor' in analysis_mode else 'Frio'})",
            labels={'hora': 'Hora do Dia', 'count': 'Nº de Pontos'},
            color_discrete_sequence=[main_color],
            template="plotly_white"
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        # Relação FRP x Confiança (modo calor) ou Temperatura x Confiança (modo frio)
        if "Calor" in analysis_mode and 'frp' in df_alerts.columns and df_alerts['frp'].notna().any():
            fig_scatter = px.scatter(
                df_alerts, x="confidence", y="frp",
                color="frp",
                title="Correlação: Confiança vs. Potência Radiativa (FRP)",
                labels={'confidence': 'Confiança (%)', 'frp': 'FRP (MW)'},
                color_continuous_scale="YlOrRd",
                template="plotly_white"
            )
        else:
            fig_scatter = px.scatter(
                df_alerts, x="confidence", y="temperature_c",
                color="temperature_c",
                title="Correlação: Confiança vs. Temperatura",
                labels={'confidence': 'Confiança (%)', 'temperature_c': 'Temperatura (°C)'},
                color_continuous_scale=color_scale,
                template="plotly_white"
            )
        st.plotly_chart(fig_scatter, use_container_width=True)

    # 8. TABELA DE REGISTROS
    st.markdown("### 📋 Registros Filtrados")
    table_cols = ['reading_timestamp', 'confidence', 'severity']
    if 'frp' in df_alerts.columns:
        table_cols.insert(1, 'frp')
    table_cols.append('temperature_k')
    display_df = df_alerts[table_cols].sort_values('reading_timestamp', ascending=False).head(15).copy()
    display_df = display_df.rename(columns={
        'frp': 'FRP (MW)', 
        'temperature_k': 'Brightness (K)',
        'confidence': 'Confiança (%)',
        'severity': 'Severidade',
        'reading_timestamp': 'Horário'
    })
    st.dataframe(display_df, use_container_width=True)

st.markdown("---")
st.caption(f"Dados atualizados em: {datetime.now().strftime('%H:%M:%S')} | Modo de Análise Regional Ativado")
