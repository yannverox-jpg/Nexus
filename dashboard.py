import streamlit as st
import subprocess
import sqlite3
import os
import sys
import psutil
import glob
import time
import json
from datetime import datetime


# ============================================================
# NEXUS OS - DASHBOARD
# ============================================================
#
# INTERFACE VISUELLE DU RUNTIME NEXUS
#
# PRINCIPES :
#   - aucune activité fictive
#   - aucun résultat généré artificiellement
#   - aucune IA simulée
#   - affichage des événements réellement écrits par Nexus
#   - visualisation type NO-CODE / BUILD PIPELINE
#   - suivi des commandes
#   - suivi des agents
#   - suivi des étapes
#   - suivi des URLs et actions web
#   - suivi des résultats
#
# Le dashboard ne décide pas ce que fait Nexus.
# Il observe le runtime.
#
# ============================================================


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "nexus_memory.db"
)

PYTHON_EXECUTABLE = sys.executable

st.set_page_config(
    page_title="Nexus OS - Command Center",
    page_icon="🛡️",
    layout="wide",
)


# ============================================================
# OUTILS
# ============================================================

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def connect_db():

    return sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False
    )


# ============================================================
# BASE DE DONNÉES
# ============================================================

def init_db():

    conn = connect_db()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Table historique existante
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Commandes
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # NOUVEAU :
    # Événements détaillés du runtime
    #
    # Cette table est le pont entre Nexus et l'interface.
    # Les modules runtime doivent y écrire leurs événements.
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            agent TEXT,
            step TEXT,
            status TEXT,
            action TEXT,
            target TEXT,
            details TEXT,
            result TEXT,
            url TEXT,
            metadata TEXT
        )
        """
    )

    # --------------------------------------------------------
    # État des agents
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE,
            role TEXT,
            status TEXT,
            current_step TEXT,
            current_task TEXT,
            last_activity TEXT,
            metadata TEXT
        )
        """
    )

    # --------------------------------------------------------
    # Opportunités détectées
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            source TEXT,
            title TEXT,
            url TEXT,
            category TEXT,
            score REAL,
            status TEXT,
            description TEXT,
            metadata TEXT
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# ENREGISTREMENT D'UN ÉVÉNEMENT
# ============================================================
#
# Cette fonction est utilisable par les autres composants
# si nécessaire.
#
# IMPORTANT :
# le dashboard ne crée PAS automatiquement des événements
# "pour faire joli".
#
# Les événements doivent représenter une action réellement
# effectuée par Nexus.
# ============================================================

def record_event(
    event_type,
    agent=None,
    step=None,
    status=None,
    action=None,
    target=None,
    details=None,
    result=None,
    url=None,
    metadata=None,
):

    conn = connect_db()
    cursor = conn.cursor()

    try:

        if isinstance(metadata, dict):

            metadata = json.dumps(
                metadata,
                ensure_ascii=False
            )

        cursor.execute(
            """
            INSERT INTO nexus_events (
                timestamp,
                event_type,
                agent,
                step,
                status,
                action,
                target,
                details,
                result,
                url,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now(),
                event_type,
                agent,
                step,
                status,
                action,
                target,
                details,
                result,
                url,
                metadata,
            )
        )

        conn.commit()

        return True

    except Exception:

        return False

    finally:

        conn.close()


# ============================================================
# LECTURE DES ÉVÉNEMENTS
# ============================================================

def load_events(limit=100):

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
                event_type,
                agent,
                step,
                status,
                action,
                target,
                details,
                result,
                url,
                metadata
            FROM nexus_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )

        return cursor.fetchall()

    except Exception:

        return []

    finally:

        conn.close()


# ============================================================
# ÉTAT DU PIPELINE
# ============================================================

def get_latest_pipeline():

    events = load_events(100)

    if not events:
        return []

    pipeline = []

    for event in reversed(events):

        (
            event_id,
            timestamp,
            event_type,
            agent,
            step,
            status,
            action,
            target,
            details,
            result,
            url,
            metadata,
        ) = event

        pipeline.append(
            {
                "id": event_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "agent": agent,
                "step": step,
                "status": status,
                "action": action,
                "target": target,
                "details": details,
                "result": result,
                "url": url,
                "metadata": metadata,
            }
        )

    return pipeline


# ============================================================
# AGENTS
# ============================================================

def load_agents():

    conn = connect_db()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                agent_name,
                role,
                status,
                current_step,
                current_task,
                last_activity,
                metadata
            FROM nexus_agents
            ORDER BY agent_name
            """
        )

        return cursor.fetchall()

    except Exception:

        return []

    finally:

        conn.close()


# ============================================================
# OPPORTUNITÉS
# ============================================================

def load_opportunities(limit=50):

    conn = connect_db()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                timestamp,
                source,
                title,
                url,
                category,
                score,
                status,
                description,
                metadata
            FROM nexus_opportunities
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )

        return cursor.fetchall()

    except Exception:

        return []

    finally:

        conn.close()


# ============================================================
# ACTIVITÉS EXISTANTES
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

        return cursor.fetchall()

    except Exception:

        return []

    finally:

        conn.close()


# ============================================================
# COMMANDES
# ============================================================

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

        return cursor.fetchall()

    except Exception:

        return []

    finally:

        conn.close()


# ============================================================
# ENVOI COMMANDE
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

            cmdline = process.info.get(
                "cmdline"
            ) or []

            command = " ".join(
                cmdline
            )

            if any(
                filename in command
                for filename in [
                    "main.py",
                    "run_all.py",
                    "nexus_autonomer.py",
                    "nexus_web.py",
                    "nexus_dashboard.py",
                    "dashboard.py",
                    "web.py",
                ]
            ):

                processes.append(
                    {
                        "pid": pid,
                        "name": process.info.get(
                            "name"
                        ),
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
# LANCEMENT DES MODULES
# ============================================================

def launch_python_file(filename):

    filepath = os.path.join(
        BASE_DIR,
        filename
    )

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
# MODULES
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

        filename = os.path.basename(
            filepath
        )

        if filename not in result:

            result.append(filename)

    return sorted(result)


project_modules = scan_project_modules()


# ============================================================
# TÉLÉMÉTRIE
# ============================================================

cpu_usage = psutil.cpu_percent(
    interval=0.2
)

memory = psutil.virtual_memory()

disk = psutil.disk_usage(
    BASE_DIR
)

nexus_processes = find_nexus_processes()

core_running = process_running(
    "main.py"
)

autonomer_running = process_running(
    "nexus_autonomer.py"
)

run_all_running = process_running(
    "run_all.py"
)

web_running = process_running(
    "nexus_web.py"
)

dashboard_running = process_running(
    "dashboard.py"
)


# ============================================================
# STYLE VISUEL
# ============================================================

st.markdown(
    """
    <style>

    .pipeline-card {
        padding: 14px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.10);
        margin-bottom: 10px;
        background: rgba(20,25,35,0.65);
    }

    .pipeline-running {
        border-left: 4px solid #f59e0b;
    }

    .pipeline-success {
        border-left: 4px solid #10b981;
    }

    .pipeline-error {
        border-left: 4px solid #ef4444;
    }

    .pipeline-pending {
        border-left: 4px solid #64748b;
    }

    .step-node {
        display: inline-block;
        padding: 8px 12px;
        margin: 4px;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(30,41,59,0.8);
        font-size: 0.85rem;
    }

    .live-indicator {
        color: #10b981;
        font-weight: 700;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# TITRE
# ============================================================

st.title(
    "🛡️ Nexus OS - Centre de Contrôle Global"
)

st.caption(
    "Interface du runtime réel. "
    "Aucune activité n'est générée pour remplir l'écran."
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "🖥️ Télémétrie Nexus"
)

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
        "🟢 Autonomer actif"
    )

else:

    st.sidebar.warning(
        "🟡 Autonomer non détecté"
    )


if run_all_running:

    st.sidebar.success(
        "🟢 run_all actif"
    )

else:

    st.sidebar.warning(
        "🟡 run_all non détecté"
    )


if web_running:

    st.sidebar.success(
        "🟢 Nexus Web actif"
    )

else:

    st.sidebar.warning(
        "🟡 Nexus Web non détecté"
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

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🚀 Activité Nexus",
        "🧠 Pipeline No-Code",
        "🤖 IA & Commandement",
        "📊 Opportunités & Revenus",
        "⚙️ Modules",
    ]
)


# ============================================================
# ONGLET 1
# ============================================================

with tab1:

    st.subheader(
        "🚀 Nexus en activité"
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
            "Événements runtime",
            len(load_events(1000))
        )


    st.markdown("---")


    st.subheader(
        "📡 Flux d'activité réel"
    )

    events = load_events(50)

    if not events:

        st.info(
            "Aucun événement runtime enregistré. "
            "Nexus n'a encore transmis aucune étape à l'interface."
        )

    else:

        for event in events:

            (
                event_id,
                timestamp,
                event_type,
                agent,
                step,
                status,
                action,
                target,
                details,
                result,
                url,
                metadata,
            ) = event

            status_lower = str(
                status or ""
            ).lower()

            if status_lower in (
                "running",
                "processing",
                "active",
                "started",
            ):

                icon = "🟡"
                css_class = "pipeline-running"

            elif status_lower in (
                "completed",
                "success",
                "done",
                "finished",
            ):

                icon = "🟢"
                css_class = "pipeline-success"

            elif status_lower in (
                "error",
                "failed",
                "failure",
            ):

                icon = "🔴"
                css_class = "pipeline-error"

            else:

                icon = "⚪"
                css_class = "pipeline-pending"


            st.markdown(
                f"""
                <div class="pipeline-card {css_class}">
                    <div>
                        {icon}
                        <b>{step or event_type or "Événement"}</b>
                        &nbsp; | &nbsp;
                        {status or "unknown"}
                    </div>

                    <div style="margin-top:6px;">
                        <b>Agent :</b>
                        {agent or "non renseigné"}
                    </div>

                    <div>
                        <b>Action :</b>
                        {action or "non renseignée"}
                    </div>

                    <div>
                        <b>Cible :</b>
                        {target or "non renseignée"}
                    </div>

                    <div>
                        <b>Détails :</b>
                        {details or "aucun détail"}
                    </div>

                    <div>
                        <b>Résultat :</b>
                        {result or "aucun résultat enregistré"}
                    </div>

                    <div style="margin-top:6px; color:#94a3b8;">
                        {timestamp}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if url:

                st.code(
                    url,
                    language="text"
                )


    st.markdown("---")


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
# ONGLET 2
# ============================================================

with tab2:

    st.subheader(
        "🧠 Pipeline d'exécution Nexus"
    )

    st.caption(
        "Cette vue représente uniquement les étapes que le "
        "runtime a réellement enregistrées."
    )


    pipeline = get_latest_pipeline()


    if not pipeline:

        st.info(
            "Le pipeline est vide. "
            "Aucune étape réelle n'a encore été enregistrée."
        )

    else:

        # Dernières étapes uniques
        displayed_steps = []

        for event in pipeline:

            step = event["step"]

            if step and step not in displayed_steps:

                displayed_steps.append(step)

            if len(displayed_steps) >= 12:

                break


        for index, step in enumerate(
            displayed_steps
        ):

            if index > 0:

                st.markdown(
                    "<div style='text-align:center;'>↓</div>",
                    unsafe_allow_html=True
                )

            st.markdown(
                f"""
                <div class="step-node">
                    {index + 1}. {step}
                </div>
                """,
                unsafe_allow_html=True
            )


        st.markdown("---")

        st.subheader(
            "Dernière étape exécutée"
        )

        latest = pipeline[-1]

        st.write(
            f"**Étape :** {latest['step'] or 'non renseignée'}"
        )

        st.write(
            f"**Agent :** {latest['agent'] or 'non renseigné'}"
        )

        st.write(
            f"**Action :** {latest['action'] or 'non renseignée'}"
        )

        st.write(
            f"**Statut :** {latest['status'] or 'non renseigné'}"
        )

        if latest["url"]:

            st.write(
                f"**URL :** {latest['url']}"
            )

        if latest["details"]:

            st.write(
                f"**Détails :** {latest['details']}"
            )

        if latest["result"]:

            st.write(
                f"**Résultat :** {latest['result']}"
            )


    st.markdown("---")

    st.subheader(
        "🤖 Agents réellement enregistrés"
    )

    agents = load_agents()

    if not agents:

        st.info(
            "Aucun agent n'a encore enregistré son état."
        )

    else:

        for agent in agents:

            (
                agent_id,
                agent_name,
                role,
                status,
                current_step,
                current_task,
                last_activity,
                metadata,
            ) = agent

            st.markdown(
                f"""
                **{agent_name}**

                Rôle : `{role or "non renseigné"}`

                Statut : `{status or "non renseigné"}`

                Étape : `{current_step or "aucune"}`

                Tâche : `{current_task or "aucune"}`

                Dernière activité : `{last_activity or "inconnue"}`
                """
            )

            st.divider()


# ============================================================
# ONGLET 3
# ============================================================

with tab3:

    st.subheader(
        "🤖 IA & Centre de Commandement"
    )

    st.caption(
        "Une IA sélectionnée ici ne reçoit pas une réponse "
        "fictive du dashboard. La directive est transmise "
        "au runtime."
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
        "📨 Commandes récentes"
    )

    commands = load_commands(30)

    if commands:

        for (
            command_id,
            timestamp,
            text,
            status,
        ) in commands:

            status_text = str(
                status
            ).lower()

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
                f"""
                {icon} **#{command_id}**
                `{timestamp}`
                **{status}**
                """
            )

            st.code(
                text
            )


    else:

        st.info(
            "Aucune commande enregistrée."
        )


# ============================================================
# ONGLET 4
# ============================================================

with tab4:

    st.subheader(
        "📊 Opportunités détectées"
    )

    opportunities = load_opportunities(50)

    if not opportunities:

        st.info(
            "Aucune opportunité réellement enregistrée."
        )

    else:

        for opportunity in opportunities:

            (
                opportunity_id,
                timestamp,
                source,
                title,
                url,
                category,
                score,
                status,
                description,
                metadata,
            ) = opportunity

            st.markdown(
                f"""
                ### {title or "Opportunité sans titre"}

                **Source :** {source or "non renseignée"}

                **Catégorie :** {category or "non renseignée"}

                **Score :** {score if score is not None else "non calculé"}

                **Statut :** {status or "non renseigné"}

                **Détectée :** {timestamp}
                """
            )

            if description:

                st.write(
                    description
                )

            if url:

                st.code(
                    url
                )

            st.divider()


    st.subheader(
        "💰 Activité économique réelle"
    )

    logs = load_activity_logs(100)

    total_revenue = 0.0

    for (
        _,
        _timestamp,
        _task,
        _result,
        revenue,
    ) in logs:

        if revenue is not None:

            try:

                total_revenue += float(
                    revenue
                )

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
            "Opportunités enregistrées",
            len(opportunities)
        )


    st.markdown("---")


    st.subheader(
        "📜 Journal économique"
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
            "Aucune activité économique enregistrée."
        )


# ============================================================
# ONGLET 5
# ============================================================

with tab5:

    st.subheader(
        "⚙️ Modules disponibles dans Nexus"
    )

    st.caption(
        "La présence d'un fichier ne signifie pas que "
        "le module est actif."
    )


    for idx, filename in enumerate(
        project_modules,
        1
    ):

        filepath = os.path.join(
            BASE_DIR,
            filename
        )

        exists = os.path.exists(
            filepath
        )

        active = process_running(
            filename
        )

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
        "🚀 Lancement manuel"
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

            if process_running(
                selected_module
            ):

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

    if user_command and user_command.strip():

        if send_command(
            user_command
        ):

            st.success(
                "Ordre transmis au runtime Nexus."
            )

    else:

        st.warning(
            "Veuillez saisir un ordre valide."
        )


# ============================================================
# ACTUALISATION AUTOMATIQUE
# ============================================================

st.markdown("---")

col_a, col_b = st.columns(
    [3, 1]
)

with col_a:

    st.caption(
        f"Nexus OS | Dernière actualisation : {now()}"
    )

with col_b:

    auto_refresh = st.checkbox(
        "Actualisation automatique",
        value=False
    )


if auto_refresh:

    time.sleep(2)

    st.rerun()
