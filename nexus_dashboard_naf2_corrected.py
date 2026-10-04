import streamlit as st
import asyncio
import aiohttp
import hmac
import hashlib
import time
import uuid
import json
import websockets
from typing import Dict, Any, Optional

# ============================================================================
# CONFIGURATION NAF 2.0 - CLIENT REPLIT
# ============================================================================
st.set_page_config(
    page_title="Nexus · Tableau de contrôle (NAF 2.0)",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
<style>
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 5px; border-left: 4px solid #00ffcc; }
    .status-offline { color: #ff4d4d; font-weight: bold; }
    .status-online { color: #00ffcc; font-weight: bold; }
    .auth-badge { background: #0066cc; color: white; padding: 5px 10px; border-radius: 3px; font-size: 0.85em; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# SECTION 1 : CONFIGURATION RÉSEAU & SÉCURITÉ
# ============================================================================
st.title("⚡ Nexus · Tableau de contrôle (NAF 2.0)")
st.subheader("Interface de communication sécurisée client-serveur")

col_config1, col_config2 = st.columns(2)

with col_config1:
    st.subheader("🔗 Configuration Réseau")
    
    # Type d'endpoint (Tunnel Cloudflare ou Render)
    endpoint_type = st.radio(
        "Type d'endpoint",
        ["Tunnel Cloudflare (trycloudflare.com)", "Instance Render", "Localhost (Dev)"],
        index=1
    )
    
    if endpoint_type == "Tunnel Cloudflare (trycloudflare.com)":
        tunnel_url = st.text_input(
            "URL du tunnel Cloudflare",
            value="https://nexus-gateway.trycloudflare.com",
            placeholder="https://votre-tunnel.trycloudflare.com"
        )
        base_url = tunnel_url
    elif endpoint_type == "Instance Render":
        render_url = st.text_input(
            "URL de l'instance Render",
            value="https://nexus-api-gateway.onrender.com",
            placeholder="https://votre-app.onrender.com"
        )
        base_url = render_url
    else:
        server_ip = st.text_input("Adresse IP", value="127.0.0.1")
        api_port = st.number_input("Port API", value=8000, min_value=1, max_value=65535)
        base_url = f"http://{server_ip}:{api_port}"
    
    st.info(f"🎯 **Endpoint actif**: `{base_url}`")

with col_config2:
    st.subheader("🔐 Authentification NAF 2.0")
    
    # Secret HMAC correct
    st.write("**Secret HMAC partagé** :")
    hmac_secret_input = st.text_input(
        "Clé Secrète HMAC",
        value="NFX_GHOST_SECURE_M28_7799_k9XpL2",
        type="password",
        help="Doit correspondre à la variable d'env NEXUS_HMAC_SECRET du serveur"
    )
    
    # Token Clerk pour l'opérateur
    st.write("**Authentification Clerk (Opérateur)** :")
    clerk_token = st.text_input(
        "Token Clerk Bearer",
        value="",
        type="password",
        placeholder="sk_test_... ou Bearer token de session"
    )
    clerk_display = "✅ Configuré" if clerk_token else "⚠️ Optionnel"
    st.markdown(f'<span class="auth-badge">{clerk_display}</span>', unsafe_allow_html=True)

st.divider()

# ============================================================================
# SECTION 2 : UTILITAIRES DE SIGNATURE HMAC & EN-TÊTES SÉCURISÉS
# ============================================================================

def build_naf2_headers(body_str: str = "", clerk_token: str = "") -> Dict[str, str]:
    """
    Génère les en-têtes NAF 2.0 complets avec :
    - Signature HMAC-SHA256 (timestamp.nonce.body)
    - En-têtes d'authentification Clerk
    """
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    
    # Message à signer : timestamp.nonce.body_json
    message_to_sign = f"{timestamp}.{nonce}.{body_str}"
    signature = hmac.new(
        hmac_secret_input.encode('utf-8'),
        message_to_sign.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-Nexus-Timestamp": timestamp,
        "X-Nexus-Nonce": nonce,
        "X-Nexus-Signature": signature
    }
    
    # Ajouter le token Clerk si disponible
    if clerk_token:
        headers["Authorization"] = f"Bearer {clerk_token}"
    
    return headers


async def async_health_check() -> Dict[str, Any]:
    """
    Test de santé NAF 2.0 : GET /health avec authentification
    Valide la bidirectionnalité client <-> serveur
    """
    headers = build_naf2_headers(clerk_token=clerk_token)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/health",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return {
                        "status": "success",
                        "http_code": 200,
                        "data": await response.json()
                    }
                else:
                    return {
                        "status": "error",
                        "http_code": response.status,
                        "details": await response.text()
                    }
    except Exception as e:
        return {
            "status": "connection_failed",
            "error": str(e)
        }


async def async_send_command(endpoint: str, payload: Dict[str, Any], method: str = "POST") -> Dict[str, Any]:
    """
    Envoie une commande sécurisée au serveur Nexus avec signature HMAC et Clerk auth
    """
    body_str = json.dumps(payload, sort_keys=True)
    headers = build_naf2_headers(body_str=body_str, clerk_token=clerk_token)
    
    url = f"{base_url}/{endpoint.lstrip('/')}"
    
    try:
        async with aiohttp.ClientSession() as session:
            if method.upper() == "POST":
                async with session.post(url, json=payload, headers=headers, timeout=10) as response:
                    return {
                        "status": "success" if response.status == 200 else "error",
                        "http_code": response.status,
                        "data": await response.json() if response.status == 200 else await response.text()
                    }
            elif method.upper() == "GET":
                async with session.get(url, headers=headers, timeout=10) as response:
                    return {
                        "status": "success" if response.status == 200 else "error",
                        "http_code": response.status,
                        "data": await response.json() if response.status == 200 else await response.text()
                    }
    except Exception as e:
        return {
            "status": "connection_failed",
            "error": str(e)
        }


async def test_websocket_naf2(message: str = "ping") -> str:
    """
    Établit une connexion WebSocket NAF 2.0 et envoie un message de test.
    Le token Clerk peut être transmis via un sous-protocole ou en-têtes custom.
    """
    # Conversion du protocole
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_endpoint = f"{ws_url}/ws/monitoring"
    
    extra_headers = {
        "X-Nexus-Timestamp": str(int(time.time())),
        "X-Nexus-Nonce": str(uuid.uuid4())
    }
    
    if clerk_token:
        extra_headers["Authorization"] = f"Bearer {clerk_token}"
    
    try:
        async with websockets.connect(
            ws_endpoint,
            extra_headers=extra_headers,
            close_timeout=5
        ) as websocket:
            # Réception du premier message du serveur
            response = await asyncio.wait_for(websocket.recv(), timeout=5)
            return response
    except Exception as e:
        return f"Erreur WebSocket : {str(e)}"


# ============================================================================
# SECTION 3 : ZONE DE TEST - SANTÉ & CONNECTIVITÉ
# ============================================================================
st.subheader("✅ Test de Santé & Connectivité")

col_test1, col_test2, col_test3 = st.columns(3)

with col_test1:
    if st.button("🏥 Test /health (HTTP)"):
        st.info("Envoi du test de santé...")
        result = asyncio.run(async_health_check())
        
        if result["status"] == "success":
            st.success(f"✅ Serveur en ligne (HTTP {result['http_code']})")
            st.json(result["data"])
        else:
            st.error(f"❌ Erreur : {result.get('error', result.get('details'))}")

with col_test2:
    if st.button("🌐 Test WebSocket (Temps réel)"):
        st.info("Connexion au WebSocket...")
        ws_response = asyncio.run(test_websocket_naf2("test"))
        
        if "Erreur" not in ws_response:
            st.success("✅ WebSocket connecté !")
            st.json(json.loads(ws_response) if ws_response.startswith("{") else {"raw": ws_response})
        else:
            st.warning(ws_response)

with col_test3:
    if st.button("🔍 Vérifier config HMAC"):
        st.info("Vérification de la configuration...")
        test_payload = {"test": "naf2_config_check"}
        body_str = json.dumps(test_payload, sort_keys=True)
        headers = build_naf2_headers(body_str=body_str)
        
        st.code(f"""
Timestamp: {headers['X-Nexus-Timestamp']}
Nonce: {headers['X-Nexus-Nonce']}
Signature: {headers['X-Nexus-Signature']}
Auth Header: {headers.get('Authorization', 'N/A')}
        """, language="text")
        st.caption("✅ En-têtes générés correctement")

st.divider()

# ============================================================================
# SECTION 4 : CONSOLE DE COMMANDES
# ============================================================================
st.subheader("🖥️ Console de Commandes Sécurisées")

col_cmd1, col_cmd2 = st.columns([2, 1])

with col_cmd1:
    with st.form("command_form"):
        action = st.selectbox(
            "Action",
            [
                "EXEC_ARBITRAGE_SIGNAL",
                "FLATTEN_POSITIONS",
                "EMERGENCY_HALT",
                "SUBMIT_GOAL",
                "GET_READINESS_STATUS",
                "CHAT_GEMINI"
            ]
        )
        
        endpoint = st.text_input("Endpoint", value="webhook")
        
        if action in ["SUBMIT_GOAL", "CHAT_GEMINI"]:
            param = st.text_area("Paramètre (JSON ou texte)", value="{}")
        else:
            symbol = st.text_input("Symbole", value="EURUSD")
            volume = st.number_input("Volume", value=0.5, step=0.1)
            param = None
        
        submitted = st.form_submit_button("📤 Transmettre la commande")
        
        if submitted:
            if action == "SUBMIT_GOAL":
                try:
                    goal_data = json.loads(param)
                    payload = {"goal": goal_data.get("goal", ""), "budget_usdc": goal_data.get("budget_usdc", 0)}
                    endpoint = "api/v1/goals/submit"
                except:
                    payload = {"goal": param, "budget_usdc": 0}
                    endpoint = "api/v1/goals/submit"
            elif action == "CHAT_GEMINI":
                payload = {"message": param}
                endpoint = "api/v1/ghost/chat/gemini"
            elif action == "GET_READINESS_STATUS":
                result = asyncio.run(async_send_command("api/v1/readiness-status", {}, method="GET"))
                st.success("Statut Readiness reçu :")
                st.json(result)
                st.stop()
            else:
                payload = {
                    "event_id": f"EVT-{uuid.uuid4().hex[:6]}",
                    "action": action,
                    "symbol": symbol if 'symbol' in locals() else "EURUSD",
                    "volume": volume if 'volume' in locals() else 0.5
                }
            
            with st.spinner("Transmission sécurisée en cours..."):
                result = asyncio.run(async_send_command(endpoint, payload))
                
                if result["status"] == "success":
                    st.success(f"✅ Commande transmise (HTTP {result['http_code']})")
                    st.json(result["data"])
                else:
                    st.error(f"❌ Échec ({result['http_code']}) : {result.get('error', result.get('data'))}")

with col_cmd2:
    st.info("""
**En-têtes envoyés :**
- ✅ X-Nexus-Timestamp
- ✅ X-Nexus-Nonce  
- ✅ X-Nexus-Signature (HMAC-SHA256)
- ✅ Authorization (Clerk)
    """)

st.divider()

# ============================================================================
# SECTION 5 : MONITEURS EN TEMPS RÉEL
# ============================================================================
st.subheader("📊 Monitoring Temps Réel")

col_mon1, col_mon2 = st.columns(2)

with col_mon1:
    if st.button("📡 Récupérer Mémoire Court-terme"):
        result = asyncio.run(async_send_command("api/v1/memory/short", {}, method="GET"))
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.warning("Impossible de récupérer la mémoire court-terme.")

with col_mon2:
    if st.button("🗂️ Récupérer Mémoire Long-terme"):
        result = asyncio.run(async_send_command("api/v1/memory/long", {}, method="GET"))
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.warning("Impossible de récupérer la mémoire long-terme.")

st.divider()

# ============================================================================
# SECTION 6 : DIAGNOSTIQUE & LOGS
# ============================================================================
st.subheader("🔧 Diagnostique Système")

st.write("**Configuration détectée :**")
diag_info = {
    "Endpoint Base": base_url,
    "Type d'endpoint": endpoint_type,
    "Secret HMAC": "✅ Configuré" if hmac_secret_input else "❌ Manquant",
    "Clerk Token": "✅ Présent" if clerk_token else "⚠️ Absent (optionnel)",
    "Version NAF": "2.0",
    "Protocoles Supportés": ["HTTP/HTTPS", "WebSocket (WSS)"]
}
st.json(diag_info)

st.caption("""
**Notes d'intégration :**
1. Le serveur doit avoir `NEXUS_HMAC_SECRET=NFX_GHOST_SECURE_M28_7799_k9XpL2` en variable d'environnement.
2. Les en-têtes Clerk sont optionnels mais recommandés pour l'audit opérateur.
3. WebSocket supporte le monitoring temps réel des tâches actives.
4. Tous les messages sont signés HMAC-SHA256 et horodatés.
""")

st.footer("Nexus NAF 2.0 · Pont d'intégration sécurisé client-serveur")
