```python
from flask import Flask, render_template_string, request, redirect, url_for, jsonify
import sqlite3
import datetime
import os

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nexus_memory.db")


def get_db():
    """
    Ouvre toujours la même base Nexus, quel que soit
    le répertoire depuis lequel Flask est lancé.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# INITIALISATION / COMPATIBILITÉ DE LA BASE
# ============================================================

def ensure_column(cursor, table_name, column_name, column_type):
    """
    Ajoute une colonne uniquement si elle n'existe pas déjà.
    Permet de conserver les anciennes bases Nexus.
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}

    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def init_web_db():
    conn = get_db()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Objectifs
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT,
            target_amount REAL,
            current_amount REAL,
            status TEXT
        )
    """)

    # --------------------------------------------------------
    # Départements
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_code TEXT UNIQUE,
            dept_name TEXT,
            status TEXT,
            active_tasks_count INTEGER,
            cpu_load TEXT,
            last_activity TEXT
        )
    """)

    # --------------------------------------------------------
    # Logs d'activité
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            department TEXT,
            task_name TEXT,
            result TEXT,
            progress_step TEXT
        )
    """)

    # Compatibilité avec une éventuelle ancienne version
    ensure_column(cursor, "actions_log", "department", "TEXT")
    ensure_column(cursor, "actions_log", "progress_step", "TEXT")

    # --------------------------------------------------------
    # Commandes
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            department TEXT,
            text TEXT,
            status TEXT,
            progress_label TEXT
        )
    """)

    ensure_column(cursor, "commands", "department", "TEXT")
    ensure_column(cursor, "commands", "progress_label", "TEXT")

    # --------------------------------------------------------
    # Identités / accès
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nexus_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            identity_type TEXT,
            access_level TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    # --------------------------------------------------------
    # Trésorerie
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treasury_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT,
            asset_name TEXT,
            amount REAL
        )
    """)

    # --------------------------------------------------------
    # NOUVEAU : événements d'exécution Nexus
    #
    # Cette table est le pont entre le moteur et l'interface.
    # Rien n'est inventé ici.
    # Les vrais composants Nexus écrivent leurs événements.
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            run_id TEXT,
            agent TEXT,
            department TEXT,
            stage TEXT,
            status TEXT,
            action TEXT,
            target TEXT,
            details TEXT,
            result TEXT,
            progress REAL
        )
    """)

    # Index pour accélérer le flux du dashboard
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_events_timestamp
        ON execution_events(timestamp)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_events_run_id
        ON execution_events(run_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_events_department
        ON execution_events(department)
    """)

    # --------------------------------------------------------
    # IMPORTANT :
    # On ne crée plus de faux soldes, faux revenus ou faux
    # états opérationnels.
    #
    # Si la base est vide, l'interface affichera simplement
    # "Aucune donnée réelle disponible".
    # --------------------------------------------------------

    conn.commit()
    conn.close()


init_web_db()


# ============================================================
# OUTIL CENTRAL DE LECTURE
# ============================================================

def get_nexus_data():
    conn = get_db()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Objectif
    # --------------------------------------------------------

    cursor.execute("""
        SELECT goal_name, target_amount, current_amount, status
        FROM performance_goals
        WHERE status = 'en_cours'
        ORDER BY id DESC
        LIMIT 1
    """)

    goal_row = cursor.fetchone()

    if goal_row:
        goal_name = goal_row["goal_name"]
        target = goal_row["target_amount"] or 0
        current = goal_row["current_amount"] or 0
        progress = (current / target * 100) if target > 0 else 0
    else:
        goal_name = "Aucun objectif actif"
        target = 0
        current = 0
        progress = 0

    # --------------------------------------------------------
    # Départements
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            dept_code,
            dept_name,
            status,
            active_tasks_count,
            cpu_load,
            last_activity
        FROM departments
        ORDER BY id
    """)

    departments = [dict(row) for row in cursor.fetchall()]

    # --------------------------------------------------------
    # Trésorerie
    # --------------------------------------------------------

    cursor.execute("""
        SELECT asset_name, amount
        FROM treasury_balances
        WHERE asset_type = 'fiat'
        ORDER BY id
    """)

    fiat = {
        row["asset_name"]: row["amount"]
        for row in cursor.fetchall()
    }

    cursor.execute("""
        SELECT asset_name, amount
        FROM treasury_balances
        WHERE asset_type = 'crypto'
        ORDER BY id
    """)

    crypto = {
        row["asset_name"]: row["amount"]
        for row in cursor.fetchall()
    }

    # --------------------------------------------------------
    # Identités
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            full_name,
            identity_type,
            access_level,
            status,
            created_at
        FROM nexus_identities
        ORDER BY id DESC
    """)

    identities = [tuple(row) for row in cursor.fetchall()]

    # --------------------------------------------------------
    # Logs classiques
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            timestamp,
            department,
            task_name,
            result,
            progress_step
        FROM actions_log
        ORDER BY id DESC
        LIMIT 20
    """)

    logs = [tuple(row) for row in cursor.fetchall()]

    # --------------------------------------------------------
    # Commandes
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            timestamp,
            department,
            text,
            status,
            progress_label
        FROM commands
        ORDER BY id DESC
        LIMIT 20
    """)

    commands = [tuple(row) for row in cursor.fetchall()]

    # --------------------------------------------------------
    # Événements d'exécution
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            timestamp,
            run_id,
            agent,
            department,
            stage,
            status,
            action,
            target,
            details,
            result,
            progress
        FROM execution_events
        ORDER BY id DESC
        LIMIT 50
    """)

    execution_events = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "goal_name": goal_name,
        "target": target,
        "current": current,
        "progress": min(progress, 100.0),
        "departments": departments,
        "fiat": fiat,
        "crypto": crypto,
        "identities": identities,
        "logs": logs,
        "commands": commands,
        "execution_events": execution_events
    }


# ============================================================
# TEMPLATE
# ============================================================

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Nexus OS - Command Center</title>

    <style>

        :root {
            --bg-base: #090d16;
            --bg-card: rgba(30, 41, 59, 0.72);
            --border-card: rgba(255,255,255,0.08);

            --blue: #38bdf8;
            --green: #10b981;
            --purple: #8b5cf6;
            --orange: #f59e0b;
            --red: #ef4444;

            --text: #f8fafc;
            --muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 25px;

            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

            background: var(--bg-base);
            color: var(--text);

            background-image:
                radial-gradient(
                    circle at 10% 20%,
                    rgba(56,189,248,.06),
                    transparent 40%
                ),
                radial-gradient(
                    circle at 90% 80%,
                    rgba(139,92,246,.06),
                    transparent 40%
                );
        }

        .container {
            max-width: 1500px;
            margin: auto;
        }

        /* ====================================================
           HEADER
        ==================================================== */

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;

            padding: 20px 25px;
            margin-bottom: 20px;

            border: 1px solid var(--border-card);
            border-radius: 16px;

            background: var(--bg-card);
            backdrop-filter: blur(16px);
        }

        .header h1 {
            margin: 0;

            background:
                linear-gradient(
                    90deg,
                    var(--blue),
                    var(--purple)
                );

            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .system-status {
            display: flex;
            align-items: center;
            gap: 8px;

            color: var(--green);
            font-size: .9rem;
            font-weight: 700;
        }

        .pulse {
            width: 10px;
            height: 10px;

            border-radius: 50%;
            background: var(--green);

            box-shadow:
                0 0 10px var(--green);

            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {

            0% {
                opacity: .5;
                transform: scale(.9);
            }

            50% {
                opacity: 1;
                transform: scale(1.15);
            }

            100% {
                opacity: .5;
                transform: scale(.9);
            }
        }

        /* ====================================================
           CARDS
        ==================================================== */

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);

            border-radius: 16px;
            padding: 20px;

            backdrop-filter: blur(16px);

            box-shadow:
                0 10px 30px rgba(0,0,0,.25);
        }

        .section-title {
            margin: 25px 0 12px;

            color: var(--muted);

            font-size: .85rem;
            font-weight: 700;

            letter-spacing: 1px;
            text-transform: uppercase;
        }

        /* ====================================================
           WORKFLOW NO-CODE
        ==================================================== */

        .workflow {
            display: flex;

            gap: 8px;

            overflow-x: auto;

            padding-bottom: 8px;
        }

        .stage {
            min-width: 125px;

            padding: 14px;

            border: 1px solid var(--border-card);
            border-radius: 12px;

            background: rgba(15,23,42,.75);

            text-align: center;

            position: relative;
        }

        .stage.active {
            border-color: var(--blue);

            box-shadow:
                0 0 20px rgba(56,189,248,.15);
        }

        .stage.done {
            border-color: rgba(16,185,129,.5);
        }

        .stage.error {
            border-color: rgba(239,68,68,.6);
        }

        .stage-icon {
            font-size: 1.3rem;
            margin-bottom: 5px;
        }

        .stage-name {
            font-size: .78rem;
            font-weight: 700;
        }

        .stage-status {
            margin-top: 5px;

            color: var(--muted);

            font-size: .68rem;
        }

        .stage-arrow {
            display: flex;
            align-items: center;

            color: var(--muted);
        }

        /* ====================================================
           LIVE ACTIVITY
        ==================================================== */

        .live-grid {
            display: grid;

            grid-template-columns:
                1.1fr
                2fr;

            gap: 20px;
        }

        .activity {
            max-height: 520px;
            overflow-y: auto;
        }

        .event {
            display: grid;

            grid-template-columns:
                75px
                120px
                1fr;

            gap: 10px;

            padding: 12px 0;

            border-bottom:
                1px solid rgba(255,255,255,.05);
        }

        .event-time {
            color: var(--muted);
            font-size: .72rem;
        }

        .event-agent {
            color: var(--blue);
            font-size: .75rem;
            font-weight: 700;
        }

        .event-details {
            font-size: .82rem;
        }

        .event-stage {
            display: inline-block;

            margin-right: 6px;
            padding: 3px 7px;

            border-radius: 8px;

            background: rgba(56,189,248,.1);

            color: var(--blue);

            font-size: .68rem;
            font-weight: 700;
        }

        .status-running {
            color: var(--blue);
        }

        .status-completed {
            color: var(--green);
        }

        .status-error {
            color: var(--red);
        }

        /* ====================================================
           AGENTS
        ==================================================== */

        .agent {
            padding: 14px;

            margin-bottom: 10px;

            border:
                1px solid var(--border-card);

            border-radius: 12px;

            background: rgba(15,23,42,.65);
        }

        .agent-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .agent-name {
            font-weight: 700;
        }

        .agent-state {
            font-size: .72rem;
        }

        .agent-task {
            margin-top: 8px;

            color: var(--muted);

            font-size: .78rem;
        }

        /* ====================================================
           DEPARTMENTS
        ==================================================== */

        .grid-departments {
            display: grid;

            grid-template-columns:
                repeat(4, 1fr);

            gap: 15px;
        }

        .dept-card {
            cursor: pointer;

            transition:
                transform .2s,
                border-color .2s;
        }

        .dept-card:hover {
            transform: translateY(-2px);
            border-color: rgba(56,189,248,.4);
        }

        .dept-name {
            color: var(--blue);
            font-weight: 700;
        }

        .metric {
            margin-top: 8px;

            color: var(--muted);
            font-size: .78rem;
        }

        /* ====================================================
           GRID
        ==================================================== */

        .grid-2 {
            display: grid;

            grid-template-columns:
                2fr
                1fr;

            gap: 20px;
        }

        /* ====================================================
           FORMS
        ==================================================== */

        textarea,
        select,
        input {

            width: 100%;

            padding: 12px;

            margin-top: 8px;

            border:
                1px solid var(--border-card);

            border-radius: 10px;

            background: rgba(15,23,42,.9);

            color: white;

            font-family: inherit;
        }

        .btn {
            width: 100%;

            padding: 12px;

            margin-top: 10px;

            border: 0;
            border-radius: 10px;

            background:
                linear-gradient(
                    135deg,
                    #3b82f6,
                    #2563eb
                );

            color: white;

            font-weight: 700;

            cursor: pointer;
        }

        /* ====================================================
           DRAWERS
        ==================================================== */

        .drawer-overlay {

            display: none;

            position: fixed;

            inset: 0;

            background:
                rgba(0,0,0,.65);

            backdrop-filter: blur(5px);

            z-index: 1000;
        }

        .drawer {

            position: fixed;

            top: 0;
            right: -520px;

            width: 500px;
            max-width: 95vw;

            height: 100%;

            padding: 25px;

            overflow-y: auto;

            background: #111827;

            border-left:
                1px solid var(--border-card);

            box-shadow:
                -20px 0 50px rgba(0,0,0,.7);

            z-index: 1001;

            transition:
                right .35s ease;
        }

        .drawer.open {
            right: 0;
        }

        .drawer-close {

            float: right;

            border: 0;
            background: none;

            color: var(--muted);

            font-size: 1.8rem;

            cursor: pointer;
        }

        .drawer h2 {
            color: var(--blue);
        }

        /* ====================================================
           RESPONSIVE
        ==================================================== */

        @media(max-width: 1000px) {

            .grid-departments {
                grid-template-columns:
                    repeat(2, 1fr);
            }

            .live-grid,
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }

        @media(max-width: 600px) {

            body {
                padding: 12px;
            }

            .grid-departments {
                grid-template-columns: 1fr;
            }

            .event {
                grid-template-columns: 65px 90px 1fr;
            }
        }

    </style>
</head>

<body>

<div class="container">

    <!-- ====================================================
         HEADER
    ===================================================== -->

    <div class="header">

        <h1>
            ✨ Nexus OS
        </h1>

        <div class="system-status">
            <div class="pulse"></div>
            Runtime connecté
        </div>

    </div>


    <!-- ====================================================
         WORKFLOW
    ===================================================== -->

    <div class="section-title">
        Flux d'exécution Nexus
    </div>

    <div class="card">

        <div class="workflow">

            {% for stage in workflow %}

                <div class="stage
                    {% if stage.status == 'RUNNING' %}active{% endif %}
                    {% if stage.status == 'COMPLETED' %}done{% endif %}
                    {% if stage.status == 'ERROR' %}error{% endif %}
                ">

                    <div class="stage-icon">
                        {{ stage.icon }}
                    </div>

                    <div class="stage-name">
                        {{ stage.name }}
                    </div>

                    <div class="stage-status">
                        {{ stage.status }}
                    </div>

                </div>

                {% if not loop.last %}
                    <div class="stage-arrow">→</div>
                {% endif %}

            {% endfor %}

        </div>

    </div>


    <!-- ====================================================
         LIVE CENTER
    ===================================================== -->

    <div class="section-title">
        Activité réelle de Nexus
    </div>

    <div class="live-grid">

        <!-- AGENTS -->

        <div class="card">

            <h3>
                Agents / processus actifs
            </h3>

            {% if agents %}

                {% for agent in agents %}

                    <div class="agent">

                        <div class="agent-header">

                            <span class="agent-name">
                                {{ agent.agent or "Agent Nexus" }}
                            </span>

                            <span class="agent-state
                                {% if agent.status == 'RUNNING' %}
                                    status-running
                                {% elif agent.status == 'COMPLETED' %}
                                    status-completed
                                {% elif agent.status == 'ERROR' %}
                                    status-error
                                {% endif %}
                            ">
                                {{ agent.status or "UNKNOWN" }}
                            </span>

                        </div>

                        <div class="agent-task">

                            {% if agent.action %}
                                {{ agent.action }}
                            {% else %}
                                Activité détectée
                            {% endif %}

                            {% if agent.details %}
                                <br>{{ agent.details }}
                            {% endif %}

                        </div>

                    </div>

                {% endfor %}

            {% else %}

                <div style="color:var(--muted); padding:20px 0;">
                    Aucun agent actif détecté par le runtime.
                </div>

            {% endif %}

        </div>


        <!-- EVENTS -->

        <div class="card activity">

            <h3>
                Flux d'exécution
            </h3>

            {% if data.execution_events %}

                {% for event in data.execution_events %}

                    <div class="event">

                        <div class="event-time">
                            {{ event.timestamp }}
                        </div>

                        <div class="event-agent">
                            {{ event.agent or "Nexus" }}
                        </div>

                        <div class="event-details">

                            <span class="event-stage">
                                {{ event.stage or "SYSTEM" }}
                            </span>

                            <span class="
                                {% if event.status == 'RUNNING' %}
                                    status-running
                                {% elif event.status == 'COMPLETED' %}
                                    status-completed
                                {% elif event.status == 'ERROR' %}
                                    status-error
                                {% endif %}
                            ">
                                {{ event.status or "UNKNOWN" }}
                            </span>

                            <br>

                            <b>
                                {{ event.action or "Événement" }}
                            </b>

                            {% if event.target %}
                                <br>
                                <span style="color:var(--muted);">
                                    {{ event.target }}
                                </span>
                            {% endif %}

                            {% if event.details %}
                                <br>
                                {{ event.details }}
                            {% endif %}

                            {% if event.result %}
                                <br>
                                <span style="color:var(--green);">
                                    Résultat : {{ event.result }}
                                </span>
                            {% endif %}

                        </div>

                    </div>

                {% endfor %}

            {% else %}

                <div style="color:var(--muted); padding:20px 0;">
                    Aucun événement d'exécution enregistré.
                </div>

            {% endif %}

        </div>

    </div>


    <!-- ====================================================
         OBJECTIF
    ===================================================== -->

    <div class="section-title">
        Objectif global
    </div>

    <div class="card">

        <div style="
            display:flex;
            justify-content:space-between;
            gap:20px;
            flex-wrap:wrap;
        ">

            <div>

                <span style="color:var(--muted);">
                    OBJECTIF
                </span>

                <h2 style="margin:5px 0;">
                    {{ data.goal_name }}
                </h2>

            </div>

            <div>

                {% if data.target > 0 %}

                    <b style="color:var(--green);">
                        {{ "%.2f"|format(data.current) }} $
                    </b>

                    <span style="color:var(--muted);">
                        / {{ "%.2f"|format(data.target) }} $
                    </span>

                {% else %}

                    <span style="color:var(--muted);">
                        Données financières non configurées
                    </span>

                {% endif %}

            </div>

        </div>

        {% if data.target > 0 %}

            <div style="
                margin-top:15px;
                height:18px;
                background:#0f172a;
                border-radius:10px;
                overflow:hidden;
            ">

                <div style="
                    width:{{ data.progress }}%;
                    height:100%;
                    background:linear-gradient(
                        90deg,
                        #3b82f6,
                        #10b981
                    );
                "></div>

            </div>

            <div style="
                text-align:center;
                margin-top:5px;
                font-size:.75rem;
            ">
                {{ "%.1f"|format(data.progress) }} %
            </div>

        {% endif %}

    </div>


    <!-- ====================================================
         DEPARTEMENTS
    ===================================================== -->

    <div class="section-title">
        Départements Nexus
    </div>

    <div class="grid-departments">

        {% for dept in data.departments %}

            <div
                class="card dept-card"
                onclick="openDeptDrawer('{{ dept.dept_code }}')"
            >

                <div class="dept-name">
                    {{ dept.dept_name }}
                </div>

                <div class="metric">
                    Statut :
                    <span>
                        {{ dept.status or "Non renseigné" }}
                    </span>
                </div>

                <div class="metric">
                    Tâches :
                    <span>
                        {{ dept.active_tasks_count
                           if dept.active_tasks_count is not none
                           else "Non renseigné" }}
                    </span>
                </div>

                <div class="metric">
                    CPU :
                    <span>
                        {{ dept.cpu_load or "Non renseigné" }}
                    </span>
                </div>

                <div class="metric">
                    Dernière activité :
                    <span>
                        {{ dept.last_activity or "Aucune donnée" }}
                    </span>
                </div>

            </div>

        {% else %}

            <div class="card">
                Aucun département enregistré.
            </div>

        {% endfor %}

    </div>


    <!-- ====================================================
         COMMANDES / IDENTITES
    ===================================================== -->

    <div class="section-title">
        Pilotage
    </div>

    <div class="grid-2">

        <!-- COMMANDES -->

        <div class="card">

            <h3>
                🚀 Assigner une mission
            </h3>

            <form method="POST" action="/command">

                <select name="department">

                    {% for dept in data.departments %}

                        <option value="{{ dept.dept_code }}">
                            {{ dept.dept_name }}
                        </option>

                    {% endfor %}

                    {% if not data.departments %}
                        <option value="general">
                            Nexus général
                        </option>
                    {% endif %}

                </select>

                <textarea
                    name="instruction"
                    rows="3"
                    placeholder="Directive à transmettre au runtime Nexus..."
                    required
                ></textarea>

                <button class="btn" type="submit">
                    Transmettre la directive
                </button>

            </form>

        </div>


        <!-- IDENTITES -->

        <div class="card">

            <div style="
                display:flex;
                justify-content:space-between;
                align-items:center;
            ">

                <h3>
                    🪪 Identités & Accès Nexus
                </h3>

                <button
                    class="btn"
                    style="
                        width:auto;
                        margin:0;
                        background:rgba(139,92,246,.2);
                    "
                    onclick="openIdentityModal()"
                >
                    + Créer
                </button>

            </div>

            <div style="
                max-height:160px;
                overflow-y:auto;
            ">

                {% for identity in data.identities %}

                    <div style="
                        padding:8px 0;
                        border-bottom:
                            1px solid rgba(255,255,255,.05);
                    ">

                        <b>
                            {{ identity[1] }}
                        </b>

                        <br>

                        <small style="color:var(--muted);">
                            {{ identity[2] }}
                            ·
                            {{ identity[3] }}
                        </small>

                        <br>

                        <span style="color:var(--green);">
                            {{ identity[4] }}
                        </span>

                    </div>

                {% else %}

                    <div style="color:var(--muted);">
                        Aucune identité enregistrée.
                    </div>

                {% endfor %}

            </div>

        </div>

    </div>


    <!-- ====================================================
         LOGS CLASSIQUES
    ===================================================== -->

    <div class="section-title">
        Journaux Nexus
    </div>

    <div class="card">

        {% for log in data.logs %}

            <div style="
                padding:10px 0;
                border-bottom:
                    1px solid rgba(255,255,255,.05);
            ">

                <span style="color:var(--blue);">
                    {{ log[1] or "NEXUS" }}
                </span>

                ·

                <b>
                    {{ log[2] }}
                </b>

                ·

                {{ log[3] }}

                <span style="
                    float:right;
                    color:var(--muted);
                    font-size:.75rem;
                ">
                    {{ log[0] }}
                </span>

            </div>

        {% else %}

            <div style="color:var(--muted);">
                Aucun journal enregistré.
            </div>

        {% endfor %}

    </div>

</div>


<!-- ========================================================
     DRAWER DEPARTEMENT
========================================================= -->

<div
    class="drawer-overlay"
    id="drawerOverlay"
    onclick="closeDrawers()"
></div>


<div class="drawer" id="deptDrawer">

    <button
        class="drawer-close"
        onclick="closeDrawers()"
    >
        ×
    </button>

    <h2 id="drawerTitle">
        Département
    </h2>

    <p
        id="drawerDesc"
        style="color:var(--muted);"
    >
        Activité réelle enregistrée par Nexus.
    </p>

    <hr style="
        border:0;
        border-top:
            1px solid var(--border-card);
    ">

    <div id="drawerContent">
        Chargement...
    </div>

</div>


<!-- ========================================================
     DRAWER IDENTITE
========================================================= -->

<div class="drawer" id="identityDrawer">

    <button
        class="drawer-close"
        onclick="closeDrawers()"
    >
        ×
    </button>

    <h2>
        Création d'Identité & Accès
    </h2>

    <p style="color:var(--muted);">
        Enregistrement d'une ressource d'accès Nexus.
    </p>

    <form method="POST" action="/create_identity">

        <input
            type="text"
            name="full_name"
            placeholder="Nom complet ou alias"
            required
        >

        <select name="identity_type">

            <option value="Identité Civile Virtuelle">
                Identité Civile Virtuelle
            </option>

            <option value="Carte d'Accès Sécurisée">
                Carte d'Accès Sécurisée
            </option>

            <option value="Passerelle d'Authentification API">
                Passerelle d'Authentification API
            </option>

        </select>

        <select name="access_level">

            <option value="Niveau Alpha (Accès Total)">
                Niveau Alpha (Accès Total)
            </option>

            <option value="Niveau Beta (Opérationnel Restreint)">
                Niveau Beta (Opérationnel Restreint)
            </option>

            <option value="Niveau Gamma (Lecture seule)">
                Niveau Gamma (Lecture seule)
            </option>

        </select>

        <button class="btn" type="submit">
            Enregistrer
        </button>

    </form>

</div>


<script>

/* ============================================================
   REFRESH AUTOMATIQUE
   ============================================================ */

let lastEventId = 0;

function refreshExecution() {

    fetch("/api/execution")
        .then(response => response.json())
        .then(data => {

            /*
             * Recharge la page uniquement lorsqu'un nouvel
             * événement existe.
             *
             * Les événements eux-mêmes proviennent de SQLite.
             */
            if (data.latest_id > lastEventId) {

                lastEventId = data.latest_id;

                window.location.reload();

            }

        })
        .catch(() => {
            // Le runtime peut être momentanément indisponible.
            // Rien n'est inventé dans l'interface.
        });
}


/*
 * Vérification légère périodique.
 */
setInterval(refreshExecution, 1500);


/* ============================================================
   DEPARTEMENT
   ============================================================ */

function openDeptDrawer(deptCode) {

    document.getElementById(
        "drawerOverlay"
    ).style.display = "block";

    document.getElementById(
        "deptDrawer"
    ).classList.add("open");

    document.getElementById(
        "drawerTitle"
    ).innerText =
        "Département : " +
        deptCode.toUpperCase();

    document.getElementById(
        "drawerContent"
    ).innerHTML =
        "<div style='color:#94a3b8'>Chargement des événements réels...</div>";

    fetch(
        "/api/department/" +
        encodeURIComponent(deptCode) +
        "/events"
    )
    .then(response => response.json())
    .then(data => {

        const content =
            document.getElementById(
                "drawerContent"
            );

        if (!data.events.length) {

            content.innerHTML =
                "<div style='color:#94a3b8'>" +
                "Aucun événement réel enregistré pour ce département." +
                "</div>";

            return;
        }

        content.innerHTML =
            data.events.map(event => {

                return `
                    <div style="
                        padding:12px 0;
                        border-bottom:
                            1px solid rgba(255,255,255,.05);
                    ">

                        <div style="
                            color:#38bdf8;
                            font-size:.75rem;
                            font-weight:700;
                        ">
                            ${event.timestamp}
                        </div>

                        <div style="
                            margin-top:4px;
                            font-weight:700;
                        ">
                            ${event.stage || "SYSTEM"}
                            ·
                            ${event.action || "Événement"}
                        </div>

                        <div style="
                            margin-top:5px;
                            color:#94a3b8;
                            font-size:.8rem;
                        ">
                            ${event.details || ""}
                        </div>

                        ${
                            event.result
                            ? `
                                <div style="
                                    margin-top:5px;
                                    color:#10b981;
                                ">
                                    Résultat :
                                    ${event.result}
                                </div>
                              `
                            : ""
                        }

                    </div>
                `;

            }).join("");

    })
    .catch(() => {

        document.getElementById(
            "drawerContent"
        ).innerHTML =
            "<div style='color:#ef4444'>" +
            "Impossible de lire les événements du runtime." +
            "</div>";

    });
}


/* ============================================================
   IDENTITE
   ============================================================ */

function openIdentityModal() {

    document.getElementById(
        "drawerOverlay"
    ).style.display = "block";

    document.getElementById(
        "identityDrawer"
    ).classList.add("open");
}


/* ============================================================
   FERMETURE
   ============================================================ */

function closeDrawers() {

    document.getElementById(
        "drawerOverlay"
    ).style.display = "none";

    document.getElementById(
        "deptDrawer"
    ).classList.remove("open");

    document.getElementById(
        "identityDrawer"
    ).classList.remove("open");
}

</script>

</body>
</html>
"""


# ============================================================
# CONSTRUCTION DU WORKFLOW
# ============================================================

WORKFLOW_STAGES = [
    ("OBSERVE", "👁️"),
    ("DISCOVER", "🔎"),
    ("RESEARCH", "🌐"),
    ("AI_ANALYSIS", "🤖"),
    ("EVALUATE", "📊"),
    ("SELECT", "🎯"),
    ("BUILD", "🧩"),
    ("LAUNCH", "🚀"),
    ("MEASURE", "📈"),
    ("OPTIMIZE", "⚙️"),
]


def build_workflow(events):
    """
    Construit l'affichage du workflow uniquement à partir
    des événements réellement enregistrés.

    Si Nexus n'a encore rien fait, les étapes restent WAITING.
    """

    state_by_stage = {}

    for stage, _icon in WORKFLOW_STAGES:
        state_by_stage[stage] = "WAITING"

    for event in reversed(events):

        stage = event.get("stage")

        if not stage:
            continue

        stage = stage.upper()

        if stage not in state_by_stage:
            continue

        status = (event.get("status") or "").upper()

        if status == "ERROR":
            state_by_stage[stage] = "ERROR"

        elif status in ("RUNNING", "STARTED", "IN_PROGRESS"):
            state_by_stage[stage] = "RUNNING"

        elif status in ("COMPLETED", "SUCCESS", "DONE"):
            state_by_stage[stage] = "COMPLETED"

    return [
        {
            "name": stage,
            "icon": icon,
            "status": state_by_stage[stage]
        }
        for stage, icon in WORKFLOW_STAGES
    ]


# ============================================================
# AGENTS ACTIFS
# ============================================================

def get_active_agents(events):
    """
    Retourne uniquement les agents dont le dernier événement
    indique réellement une activité en cours.
    """

    latest_by_agent = {}

    for event in reversed(events):

        agent = event.get("agent")

        if not agent:
            continue

        if agent not in latest_by_agent:
            latest_by_agent[agent] = event

    active = []

    for agent, event in latest_by_agent.items():

        status = (event.get("status") or "").upper()

        if status in (
            "RUNNING",
            "STARTED",
            "IN_PROGRESS"
        ):

            active.append(event)

    return active


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():

    data = get_nexus_data()

    workflow = build_workflow(
        data["execution_events"]
    )

    agents = get_active_agents(
        data["execution_events"]
    )

    return render_template_string(
        DASHBOARD_TEMPLATE,
        data=data,
        workflow=workflow,
        agents=agents
    )


# ============================================================
# API EXECUTION
# ============================================================

@app.route("/api/execution")
def api_execution():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            timestamp,
            run_id,
            agent,
            department,
            stage,
            status,
            action,
            target,
            details,
            result,
            progress
        FROM execution_events
        ORDER BY id DESC
        LIMIT 100
    """)

    events = [
        dict(row)
        for row in cursor.fetchall()
    ]

    latest_id = events[0]["id"] if events else 0

    conn.close()

    return jsonify({
        "latest_id": latest_id,
        "events": events
    })


# ============================================================
# API DEPARTEMENT
# ============================================================

@app.route("/api/department/<dept_code>/events")
def department_events(dept_code):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            timestamp,
            run_id,
            agent,
            department,
            stage,
            status,
            action,
            target,
            details,
            result,
            progress
        FROM execution_events
        WHERE department = ?
        ORDER BY id DESC
        LIMIT 50
    """, (dept_code,))

    events = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({
        "department": dept_code,
        "events": events
    })


# ============================================================
# COMMANDE
# ============================================================

@app.route("/command", methods=["POST"])
def command():

    dept = request.form.get(
        "department",
        "general"
    )

    instruction = (
        request.form.get("instruction") or ""
    ).strip()

    if instruction:

        conn = get_db()
        cursor = conn.cursor()

        now = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Commande réelle placée dans la file
        cursor.execute("""
            INSERT INTO commands (
                timestamp,
                department,
                text,
                status,
                progress_label
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            now,
            dept,
            instruction,
            "pending",
            "En attente du runtime"
        ))

        # Trace d'activité
        cursor.execute("""
            INSERT INTO actions_log (
                timestamp,
                department,
                task_name,
                result,
                progress_step
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            now,
            dept,
            "Directive utilisateur",
            "Commande placée dans la file Nexus",
            "PENDING"
        ))

        # Événement visible dans le workflow
        cursor.execute("""
            INSERT INTO execution_events (
                timestamp,
                run_id,
                agent,
                department,
                stage,
                status,
                action,
                target,
                details,
                result,
                progress
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now,
            None,
            "Command Center",
            dept,
            "SELECT",
            "COMPLETED",
            "COMMAND_SUBMITTED",
            dept,
            instruction,
            "Commande placée dans la file",
            0
        ))

        conn.commit()
        conn.close()

    return redirect(url_for("index"))


# ============================================================
# CREATION IDENTITE
# ============================================================

@app.route("/create_identity", methods=["POST"])
def create_identity():

    full_name = (
        request.form.get("full_name") or ""
    ).strip()

    identity_type = request.form.get(
        "identity_type",
        ""
    )

    access_level = request.form.get(
        "access_level",
        ""
    )

    if full_name:

        conn = get_db()
        cursor = conn.cursor()

        now = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute("""
            INSERT INTO nexus_identities (
                full_name,
                identity_type,
                access_level,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            full_name,
            identity_type,
            access_level,
            "Actif",
            now
        ))

        cursor.execute("""
            INSERT INTO actions_log (
                timestamp,
                department,
                task_name,
                result,
                progress_step
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            now,
            "infra",
            "Création d'accès",
            f"Ressource enregistrée : {full_name}",
            "COMPLETED"
        ))

        cursor.execute("""
            INSERT INTO execution_events (
                timestamp,
                run_id,
                agent,
                department,
                stage,
                status,
                action,
                target,
                details,
                result,
                progress
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now,
            None,
            "Command Center",
            "infra",
            "BUILD",
            "COMPLETED",
            "ACCESS_RESOURCE_CREATED",
            full_name,
            identity_type,
            "Ressource enregistrée",
            0
        ))

        conn.commit()
        conn.close()

    return redirect(url_for("index"))


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
```
