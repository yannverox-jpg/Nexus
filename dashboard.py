```python
import streamlit as st
import subprocess
import sqlite3
import os
import sys
import psutil
import glob
import time
from datetime import datetime

# ============================================================
# NEXUS OS - DASHBOARD
# ============================================================
#
# Le dashboard est une INTERFACE du runtime Nexus.
# Il ne simule pas les activités.
#
# Les informations affichées doivent provenir :
#   - des processus réellement actifs
#   - de la mémoire SQLite
#   - des commandes réellement transmises
#   - des modules réellement présents
#
# ============================================================


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "nexus_memory.db")

PYTHON_EXECUTABLE = sys.executable

st.set_page_config(
    page_title="Nexus OS - Command Center",
    page_icon="🛡️",
    layout="wide",
)


# ============================================================
# TITRE
# ============================================================

st.title("🛡️ Nexus OS - Centre de Contrôle Global")

st.markdown(
    """
    **Runtime Nexus visible depuis le dashboard.**

    Le dashboard ne simule pas l'activité du système.
    Il affiche l'état réel des processus, commandes, journaux,
    modules et résultats disponibles.
    """
)


# ============================================================
# OUTILS
# ============================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect_db():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=5,
        check_same_thread=False
    )
    return conn


# ============================================================
# BASE DE DONNÉES
# ============================================================

def init_db():

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            task_name TEXT,
            result TEXT,
            revenue_generated REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            text TEXT,
            status TEXT
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# LECTURE DES ACTIVITÉS
# ============================================================

def load_activity_logs(limit=50):

    if not os.path.exists(DB_PATH):
        return []

    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                timestamp,
                task_name,
                result,
                revenue_generated
            FROM actions_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )

        rows = cursor.fetchall()

    except Exception:
        rows = []

    finally:
        conn.close()

    return rows


def load_commands(limit=30):

    if not os.path.exists(DB_PATH):
        return []

    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                timestamp,
                text,
                status
            FROM commands
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )

        rows = cursor.fetchall()

    except Exception:
        rows = []

    finally:
        conn.close()

    return rows


# ============================================================
# ENVOI D'UNE COMMANDE AU RUNTIME
# ============================================================

def send_command(command_text):

    if not command_text or not command_text.strip():
        return False

    conn = connect_db()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO commands
            (timestamp, text, status)
            VALUES (?, ?, ?)
            """,
            (
                now(),
                command_text.strip(),
                "pending",
            )
        )

        conn.commit()
        return True

    except Exception as exc:

        st.error(
            f"Impossible d'enregistrer la commande : {exc}"
        )

        return False

    finally:
        conn.close()


# ============================================================
# PROCESSUS NEXUS
# ============================================================

def find_nexus_processes():

    processes = []

    current_pid = os.getpid()

    for process in psutil.process_iter(
        ["pid", "name", "cmdline"]
    ):

        try:

            pid = process.info["pid"]

            if pid == current_pid:
                continue

            cmdline = process.info.get("cmdline") or []

            command = " ".join(cmdline)

            if any(
                filename in command
                for filename in [
                    "main.py",
                    "run_all.py",
                    "nexus_autonomer.py",
                    "nexus_web.py",
                    "nexus_dashboard.py",
                    "dashboard.py",
                ]
            ):

                processes.append(
                    {
                        "pid": pid,
                        "name": process.info.get("name"),
                        "command": command,
                    }
                )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            continue

    return processes


def process_running(filename):

    for process in find_nexus_processes():

        if filename in process["command"]:
            return True

    return False


# ============================================================
# LANCEMENT DES COMPOSANTS
# ============================================================

def launch_python_file(filename):

    filepath = os.path.join(BASE_DIR, filename)

    if not os.path.exists(filepath):

        st.error(
            f"Module introuvable : {filename}"
        )

        return None

    try:

        process = subprocess.Popen(
            [
                PYTHON_EXECUTABLE,
                filepath,
            ],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return process

    except Exception as exc:

        st.error(
            f"Erreur de lancement de {filename} : {exc}"
        )

        return None


# ============================================================
# MODULES DU PROJET
# ============================================================

def scan_project_modules():

    patterns = [
        "*.py",
        "*.sh",
        "ghost*",
    ]

    files = []

    for pattern in patterns:

        files.extend(
            glob.glob(
                os.path.join(
                    BASE_DIR,
                    pattern
                )
            )
        )

    result = []

    for filepath in files:

        filename = os.path.basename(filepath)

        if filename not in result:
            result.append(filename)

    return sorted(result)


project_modules = scan_project_modules()


# ============================================================
# TÉLÉMÉTRIE
# ============================================================

cpu_usage = psutil.cpu_percent(interval=0.2)

memory = psutil.virtual_memory()

disk = psutil.disk_usage(BASE_DIR)

nexus_processes = find_nexus_processes()

core_running = process_running("main.py")

autonomer_running = process_running("nexus_autonomer.py")

run_all_running = process_running("run_all.py")


# ============================================================
# BARRE LATÉRALE
# ============================================================

st.sidebar.header("🖥️ Télémétrie Nexus")

st.sidebar.metric(
    "CPU",
    f"{cpu_usage}%"
)

st.sidebar.metric(
    "RAM",
    f"{memory.percent}%"
)

st.sidebar.metric(
    "Stockage",
    f"{disk.percent}%"
)


st.sidebar.markdown("---")

if core_running:

    st.sidebar.success(
        "🟢 Nexus Core actif"
    )

else:

    st.sidebar.error(
        "🔴 Nexus Core arrêté"
    )


if autonomer_running:

    st.sidebar.success(
        "🟢 Nexus Autonomer actif"
    )

else:

    st.sidebar.warning(
        "🟡 Nexus Autonomer non détecté"
    )


if run_all_running:

    st.sidebar.success(
        "🟢 run_all actif"
    )

else:

    st.sidebar.warning(
        "🟡 run_all non détecté"
    )


st.sidebar.markdown("---")

st.sidebar.caption(
    f"Python : {PYTHON_EXECUTABLE}"
)

st.sidebar.caption(
    f"Base : {DB_PATH}"
)


if st.sidebar.button(
    "🔄 Actualiser maintenant",
    use_container_width=True
):

    st.rerun()


# ============================================================
# ONGLETS
# ============================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🚀 Nexus & Activités",
        "🤖 IA & Centre de Commandement",
        "📊 Activité & Revenus",
        "⚙️ Modules du serveur",
    ]
)


# ============================================================
# ONGLET 1
# ============================================================

with tab1:

    st.subheader(
        "🚀 Activité réelle du runtime Nexus"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        if core_running:
            st.success("Nexus Core\nACTIF")
        else:
            st.error("Nexus Core\nARRÊTÉ")

    with col2:

        if autonomer_running:
            st.success("Autonomer\nACTIF")
        else:
            st.warning("Autonomer\nNON DÉTECTÉ")

    with col3:

        st.metric(
            "Processus Nexus",
            len(nexus_processes)
        )

    with col4:

        st.metric(
            "Modules détectés",
            len(project_modules)
        )


    st.markdown("---")


    st.subheader(
        "🧠 Centre de commandement"
    )

    st.info(
        "Le dashboard affiche ici les informations réellement "
        "écrites dans la mémoire de Nexus. Il ne fabrique pas "
        "d'activité artificielle."
    )


    # --------------------------------------------------------
    # ACTIVITÉS RÉCENTES
    # --------------------------------------------------------

    logs = load_activity_logs(30)

    if logs:

        for (
            log_id,
            timestamp,
            task_name,
            result,
            revenue,
        ) in logs:

            col_a, col_b, col_c = st.columns(
                [2, 3, 2]
            )

            with col_a:

                st.caption(
                    timestamp
                )

            with col_b:

                st.write(
                    f"**{task_name}**"
                )

            with col_c:

                if revenue is not None:

                    st.write(
                        f"💰 {revenue:.2f} €"
                    )

                else:

                    st.write(
                        "—"
                    )

            st.caption(
                f"Résultat : {result}"
            )

            st.divider()

    else:

        st.warning(
            "Aucune activité enregistrée dans actions_log."
        )


    # --------------------------------------------------------
    # PROCESSUS
    # --------------------------------------------------------

    st.subheader(
        "⚙️ Processus réellement actifs"
    )

    if nexus_processes:

        for process in nexus_processes:

            st.code(
                f"PID {process['pid']} | "
                f"{process['command']}"
            )

    else:

        st.warning(
            "Aucun processus Nexus détecté."
        )


# ============================================================
# ONGLET 2 : IA
# ============================================================

with tab2:

    st.subheader(
        "🤖 IA & Centre de Commandement Nexus"
    )

    st.markdown(
        """
        Les IA ne sont plus simulées dans ce dashboard.

        Une directive envoyée ici est enregistrée dans la file
        `commands` afin que le runtime Nexus puisse réellement
        la traiter.
        """
    )


    selected_ai = st.selectbox(
        "IA ciblée",
        [
            "Auto / Centre de commandement",
            "GPT (OpenAI)",
            "Gemini (Google)",
            "Claude (Anthropic)",
        ]
    )


    ai_prompt = st.chat_input(
        "Directive à transmettre au runtime Nexus..."
    )


    if ai_prompt:

        command = (
            f"[AI_TARGET={selected_ai}] "
            f"{ai_prompt.strip()}"
        )

        if send_command(command):

            st.success(
                "Directive enregistrée dans le runtime Nexus."
            )

            st.code(
                command
            )


    st.markdown("---")


    st.subheader(
        "📨 Commandes en attente / récentes"
    )

    commands = load_commands(30)

    if commands:

        for (
            command_id,
            timestamp,
            text,
            status,
        ) in commands:

            status_text = str(status).lower()

            if status_text == "completed":

                icon = "🟢"

            elif status_text in (
                "running",
                "processing",
            ):

                icon = "🟡"

            elif status_text in (
                "error",
                "failed",
            ):

                icon = "🔴"

            else:

                icon = "⚪"

            st.markdown(
                f"{icon} **#{command_id}** "
                f"`{timestamp}` "
                f"**{status}**"
            )

            st.code(
                text
            )

    else:

        st.info(
            "Aucune commande enregistrée."
        )


# ============================================================
# ONGLET 3 : ACTIVITÉ / REVENUS
# ============================================================

with tab3:

    st.subheader(
        "📊 Activité économique réelle"
    )

    logs = load_activity_logs(100)

    total_revenue = 0.0

    if logs:

        for (
            _,
            _timestamp,
            _task,
            _result,
            revenue,
        ) in logs:

            if revenue is not None:

                try:
                    total_revenue += float(revenue)
                except (
                    ValueError,
                    TypeError,
                ):
                    pass


    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Revenus enregistrés",
            f"{total_revenue:.2f} €"
        )

    with col2:

        st.metric(
            "Actions enregistrées",
            len(logs)
        )

    with col3:

        st.metric(
            "Opportunités / activités",
            len(logs)
        )


    st.markdown("---")


    st.subheader(
        "📜 Journal du runtime"
    )

    if logs:

        for (
            log_id,
            timestamp,
            task_name,
            result,
            revenue,
        ) in logs:

            revenue_value = (
                f"{float(revenue):.2f} €"
                if revenue is not None
                else "—"
            )

            st.write(
                f"**{timestamp}** | "
                f"**{task_name}** | "
                f"{result} | "
                f"💰 {revenue_value}"
            )

    else:

        st.info(
            "Le runtime n'a encore enregistré aucune activité."
        )


# ============================================================
# ONGLET 4 : MODULES
# ============================================================

with tab4:

    st.subheader(
        "⚙️ Modules disponibles dans Nexus"
    )

    st.markdown(
        """
        Cette section montre les composants présents dans
        l'environnement. Un module n'est pas considéré comme
        actif simplement parce que son fichier existe.
        """
    )


    for idx, filename in enumerate(
        project_modules,
        1
    ):

        filepath = os.path.join(
            BASE_DIR,
            filename
        )

        exists = os.path.exists(filepath)

        active = process_running(filename)

        if active:

            status = "🟢 ACTIF"

        elif exists:

            status = "⚪ DISPONIBLE"

        else:

            status = "🔴 ABSENT"

        st.markdown(
            f"**{idx}. {filename}** — {status}"
        )


    st.markdown("---")


    st.subheader(
        "🚀 Lancement manuel d'un module"
    )

    module_candidates = [
        filename
        for filename in project_modules
        if filename.endswith(".py")
        and filename not in [
            "dashboard.py",
        ]
    ]


    if module_candidates:

        selected_module = st.selectbox(
            "Module",
            module_candidates
        )

        if st.button(
            "▶️ Lancer le module",
            use_container_width=True
        ):

            if process_running(selected_module):

                st.warning(
                    f"{selected_module} est déjà actif."
                )

            else:

                process = launch_python_file(
                    selected_module
                )

                if process:

                    st.success(
                        f"{selected_module} lancé "
                        f"(PID {process.pid})."
                    )

    else:

        st.info(
            "Aucun module Python disponible."
        )


# ============================================================
# COMMANDE DIRECTE
# ============================================================

st.markdown("---")

st.subheader(
    "💬 Commande directe à Nexus"
)

user_command = st.text_input(
    "Ordre global",
    placeholder=(
        "Exemple : analyse les opportunités actuellement "
        "détectées et sélectionne la meilleure."
    )
)


if st.button(
    "📡 Transmettre à Nexus",
    use_container_width=True
):

    # CORRECTION DU BUG :
    # user_command est une chaîne.
    # Il n'existe donc pas de user_command.sys.

    if user_command and user_command.strip():

        if send_command(user_command):

            st.success(
                "Ordre transmis au runtime Nexus."
            )

    else:

        st.warning(
            "Veuillez saisir un ordre valide."
        )


# ============================================================
# PIED DE PAGE
# ============================================================

st.markdown("---")

st.caption(
    f"Nexus OS | Dernière actualisation : {now()}"
)
```
