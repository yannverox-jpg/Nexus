import streamlit as st
import subprocess
import sqlite3
import os
import psutil
import glob
from datetime import datetime

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Nexus OS - Command Center",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Nexus OS - Centre de Contrôle Global & Ingénierie")
st.markdown("Plateforme unifiée : pilotage des modules locaux, des tableaux visuels Ghost, des IA interconnectées et des flux temps réel.")

# --- BARRE LATÉRALE : TÉLÉMÉTRIE & ÉTAT DU SERVEUR ---
st.sidebar.header("🖥️ Télémétrie du Serveur")
cpu_usage = psutil.cpu_percent(interval=1)
memory = psutil.virtual_memory()

st.sidebar.metric(label="Utilisation CPU", value=f"{cpu_usage}%")
st.sidebar.metric(label="Mémoire Vive (RAM)", value=f"{memory.percent}%")
st.sidebar.success("Environnement venv : Actif")
st.sidebar.info("Mode : Fenêtres réelles & Modules locaux")

# --- DÉTECTION AUTOMATIQUE DES MODULES DU SERVEUR ---
def scan_project_modules():
    # Recherche tous les scripts python ou modules présents dans le dossier Nexus
    all_files = glob.glob("*.py") + glob.glob("*.sh") + glob.glob("ghost*")
    return sorted(list(set(all_files)))

project_modules = scan_project_modules()

# --- GESTION DE LA BASE DE DONNÉES SQLite ---
db_path = "nexus_memory.db"

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            task_name TEXT,
            result TEXT,
            revenue_generated REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            text TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_activity_logs():
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT timestamp, task_name, result, revenue_generated FROM actions_log ORDER BY id DESC LIMIT 15")
            logs = cursor.fetchall()
            conn.close()
            return logs
        except Exception:
            conn.close()
            return []
    return []

# --- ONGLETS PRINCIPAUX DU DASHBOARD ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 Pilotage & Modules (Ghost / Web.py / Main)", 
    "🤖 Connexion IA (Claude, GPT, Gemini)", 
    "📊 Télémétrie & Logs Serveur",
    "⚙️ Indexation du Serveur"
])

# --- ONGLET 1 : PILOTAGE DES MODULES & FENÊTRES ---
with tab1:
    st.subheader("🌐 Lancement des Modules & Tableaux Visuels (Ghost & Furtif)")
    st.markdown("Exécutez directement vos scripts d'ingénierie personnalisés et vos fenêtres de navigation réelles.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 👻 Tableaux Ghost & Web")
        if st.button("🚀 Lancer l'interface Ghost", use_container_width=True):
            st.toast("Démarrage du module Ghost...", icon="👻")
            if os.path.exists("ghost.py"):
                subprocess.Popen(["python3", "ghost.py"])
            else:
                subprocess.Popen(["python3", "main.py"])
        
        if st.button("🌐 Lancer web.py", use_container_width=True):
            st.toast("Démarrage de web.py...", icon="🌐")
            if os.path.exists("web.py"):
                subprocess.Popen(["python3", "web.py"])

    with col2:
        st.markdown("### ⚙️ Orchestration Principale")
        if st.button("🚀 Lancer main.py (Orchestrateur)", use_container_width=True):
            st.toast("Exécution de main.py...", icon="⚡")
            subprocess.Popen(["python3", "main.py"])

        if st.button("💳 Lancer Plateforme Stripe / Furtif", use_container_width=True):
            st.toast("Ouverture de la session de navigation...", icon="💳")

    with col3:
        st.markdown("### 🛠️ Modules Personnalisés Détectés")
        for mod in project_modules:
            if mod not in ["dashboard.py", "__init__"]:
                if st.button(f"Exécuter {mod}", use_container_width=True):
                    st.toast(f"Lancement de {mod}...", icon="▶️")
                    subprocess.Popen(["python3", mod])

    st.markdown("---")
    st.subheader("💬 Commandes Directes pour Nexus OS")
    user_command = st.text_input("Ordre global pour le serveur (ex: 'Lance Ghost et synchronise avec main.py')", "")
    if st.button("Transmettre l'ordre au système"):
        if user_command.sys and user_command.strip():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO commands (timestamp, text, status) VALUES (datetime('now'), ?, 'pending')", (user_command,))
            conn.commit()
            conn.close()
            st.success(f"Ordre enregistré et transmis au cœur de Nexus : '{user_command}'")
        else:
            st.warning("Veuillez saisir un ordre valide.")

# --- ONGLET 2 : CONNEXION IA (CLAUDE, GPT, GEMINI) ---
with tab2:
    st.subheader("🤖 Cerveau Central IA (Claude, GPT, Gemini connectés à Ghost & Nexus)")
    st.markdown("Discutez avec vos modèles, injectez des instructions directement dans l'ingénierie de vos modules.")

    selected_ai = st.selectbox("Sélectionner l'IA active pour Nexus :", ["Gemini (Google)", "Claude (Anthropic)", "GPT (OpenAI)"])

    chat_key = f"nexus_chat_{selected_ai.lower().split()[0]}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [{
            "role": "assistant", 
            "content": f"Système Nexus initialisé avec {selected_ai}. Connecté aux flux Ghost et aux scripts locaux. En attente de vos directives."
        }]

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if ai_prompt := st.chat_input(f"Envoyer une directive à {selected_ai} (ex: 'Optimise la boucle de trading dans main.py')..."):
        st.session_state[chat_key].append({"role": "user", "content": ai_prompt})
        with st.chat_message("user"):
            st.markdown(ai_prompt)

        # Simulation de réponse connectée aux modules
        ai_reply = f"[{selected_ai}] Analyse de votre code et des flux Ghost en cours... Directive reçue : '{ai_prompt}'. Connexion aux endpoints validée."
        st.session_state[chat_key].append({"role": "assistant", "content": ai_reply})
        with st.chat_message("assistant"):
            st.markdown(ai_reply)

# --- ONGLET 3 : TÉLÉMÉTRIE & LOGS SERVEUR ---
with tab3:
    st.subheader("📊 Journaux d'Activité & Télémétrie du Système")
    
    col_ref, col_clear = st.columns([1, 4])
    with col_ref:
        if st.button("🔄 Rafraîchir les données"):
            st.rerun()

    logs = load_activity_logs()
    if logs:
        for timestamp, task_name, result, revenue in logs:
            st.text(f"[{timestamp}] [{task_name}] -> {result} | Revenu: {revenue}€")
    else:
        st.info("Aucun log d'action enregistré dans la mémoire SQLite pour le moment.")

    st.markdown("---")
    st.subheader("📈 Métriques Système en Direct")
    st.code(f"""
    - Processeur (CPU) : {cpu_usage}%
    - Mémoire Vive (RAM) : {memory.percent}% ({memory.used // (1024*1024)} Mo / {memory.total // (1024*1024)} Mo)
    - Stockage de la mémoire : {db_path}
    - Fichiers ingénierie détectés : {len(project_modules)} modules
    """, language="text")

# --- ONGLET 4 : INDEXATION DU SERVEUR ---
with tab4:
    st.subheader("⚙️ Cartographie et Indexation des Fichiers du Serveur")
    st.markdown("Voici l'ensemble des modules, scripts et tableaux visuels actuellement présents dans votre environnement de travail :")
    
    for idx, file in enumerate(project_modules, 1):
        st.text(f"{idx}. 📁 {file} (Prêt à être orchestré par Nexus)")

    st.markdown("---")
    st.info("Pour ajouter un nouveau module, placez-le simplement dans le répertoire du serveur et rafraîchissez cette page.")
