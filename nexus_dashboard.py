import streamlit as st
import asyncio
import aiohttp
import hmac
import hashlib
import time
import uuid
import json

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Nexus · Interface de pilotage",
    page_icon="⚡",
    layout="wide"
)

# Style CSS minimaliste de type industriel
st.markdown("""
<style>
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 5px; border-left: 4px solid #00ffcc; }
    .status-offline { color: #ff4d4d; font-weight: bold; }
    .status-online { color: #00ffcc; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# En-tête du Centre de Contrôle
st.title("⚡ Nexus · Interface de pilotage")
st.subheader("Centre de contrôle")
st.write("Transmission sécurisée de commandes vers la passerelle API et supervision temps réel de la télémétrie du cluster GPU.")

# Barre latérale de configuration de connexion
st.sidebar.header("Configuration Réseau")
server_ip = st.sidebar.text_input("Adresse IP du Serveur", value="127.0.0.1")
api_port = st.sidebar.number_input("Port API Gateway", value=8000)
metrics_port = st.sidebar.number_input("Port Télémétrie", value=9090)
secret_key = st.sidebar.text_input("Clé Secrète HMAC", value="SECURE_CORP_MASTER_KEY_9981", type="password")

base_url = f"http://{server_ip}:{api_port}"
metrics_url = f"http://{server_ip}:{metrics_port}"

# Fonction asynchrone pour tester la connexion et envoyer des commandes
async def async_send_command(endpoint: str, payload: dict):
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_str = json.dumps(payload, sort_keys=True)

    message = f"{timestamp}.{nonce}.{body_str}".encode('utf-8')
    signature = hmac.new(secret_key.encode('utf-8'), message, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Nexus-Timestamp": timestamp,
        "X-Nexus-Nonce": nonce,
        "X-Nexus-Signature": signature
    }

    url = f"{base_url}/{endpoint.lstrip('/')}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=3.0) as response:
                if response.status == 200:
                    return {"status": "success", "data": await response.json()}
                else:
                    return {"status": "error", "code": response.status, "details": await response.text()}
        except Exception as e:
            return {"status": "offline", "error": str(e)}

async def async_fetch_telemetry():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(metrics_url, timeout=2.0) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except:
            return None

# Vérification instantanée du statut (Online / Offline)
is_online = False
telemetry_data = asyncio.run(async_fetch_telemetry())
if telemetry_data is not None:
    is_online = True

# Affichage du statut en temps réel
col_status1, col_status2 = st.columns([2, 4])
with col_status1:
    st.markdown(f"**Passerelle Nexus**  \nAPI :{api_port} · Télémétrie :{metrics_port}")
with col_status2:
    if is_online:
        st.markdown('<p class="status-online">● EN LIGNE (Connecté au cluster)</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="status-offline">● HORS LIGNE (Serveur injoignable)</p>', unsafe_allow_html=True)

st.divider()

# Disposition en deux colonnes principales
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🖥️ Console de commandes")
    st.caption("Sécurité active : HMAC-SHA256")

    with st.form("command_form"):
        action = st.selectbox("Action", ["EXEC_ARBITRAGE_SIGNAL", "FLATTEN_POSITIONS", "EMERGENCY_HALT"])
        endpoint = st.text_input("Endpoint", value="webhook")
        symbol = st.text_input("Symbole", value="GOLD")
        volume = st.number_input("Volume", value=0.5, step=0.1)

        submitted = st.form_submit_button("Transmettre la commande")

        if submitted:
            payload = {
                "event_id": f"EVT-{uuid.uuid4().hex[:6]}",
                "action": action,
                "symbol": symbol,
                "volume": volume
            }
            with st.spinner("Transmission sécurisée en cours..."):
                result = asyncio.run(async_send_command(endpoint, payload))
                if result["status"] == "success":
                    st.success(f"Commande transmise avec succès : {result['data']}")
                else:
                    st.error(f"Échec de transmission ({result['status']}) : {result.get('error', result.get('details'))}")

with col_right:
    st.subheader("📊 Télémétrie du cluster")
    st.caption(f"Prometheus :{metrics_port}")

    if st.button("Récupérer les métriques live"):
        if is_online:
            st.code(telemetry_data[:1000] + "\n... [Affichage tronqué]", language="text")
        else:
            st.warning("Impossible de récupérer les métriques : Le serveur est hors ligne.")

    st.subheader("📜 Journal d'activité")
    if is_online:
        st.info("Système actif. En attente d'événements de trading ou de webhooks entrants...")
    else:
        st.warning("Aucune opération en cours (Serveur déconnecté).")

st.divider()
st.caption("Pont d'intégration Nexus · signatures HMAC-SHA256 · clé secrète stockée côté serveur")
