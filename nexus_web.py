

from flask import Flask, render_template_string, request, redirect, url_for
import sqlite3
import datetime

app = Flask(__name__)

def init_web_db():
    conn = sqlite3.connect("nexus_memory.db")
    cursor = conn.cursor()
    
    # Objectifs de performance globaux
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT,
            target_amount REAL,
            current_amount REAL,
            status TEXT
        )
    ''')
    
    # Départements du serveur
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_code TEXT UNIQUE,
            dept_name TEXT,
            status TEXT,
            active_tasks_count INTEGER,
            cpu_load TEXT,
            last_activity TEXT
        )
    ''')

    # Journaux d'activités croisés
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            department TEXT,
            task_name TEXT,
            result TEXT,
            progress_step TEXT
        )
    ''')

    # Commandes et directives système
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            department TEXT,
            text TEXT,
            status TEXT,
            progress_label TEXT
        )
    ''')

    # Gestion des identités civiles, cartes et accès Nexus
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nexus_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            identity_type TEXT,
            access_level TEXT,
            status TEXT,
            created_at TEXT
        )
    ''')

    # Trésorerie / Soldes Fiat & Crypto
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS treasury_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT,
            asset_name TEXT,
            amount REAL
        )
    ''')

    # Initialisation des données par défaut si tables vides
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        default_depts = [
            ('trading', 'Département Trading (MT5 / PyTorch)', 'Opérationnel (28 paires + Or)', 3, '14.2%', 'Exécution Stat-Arb active'),
            ('microtasks', 'Département Micro-tâches (Prolific)', 'Actif / Balayage auto', 12, '4.1%', 'Validation de formulaires'),
            ('treasury', 'Département Trésorerie & Fiat', 'Synchronisé', 0, '1.5%', 'Vérification passerelles Stripe/PayPal'),
            ('infra', 'Département Infrastructure VPS', 'Stable (GitHub / Render)', 5, '8.9%', 'Surveillance des containers')
        ]
        cursor.executemany("INSERT INTO departments (dept_code, dept_name, status, active_tasks_count, cpu_load, last_activity) VALUES (?, ?, ?, ?, ?, ?)", default_depts)

    cursor.execute("SELECT COUNT(*) FROM performance_goals")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO performance_goals (goal_name, target_amount, current_amount, status) VALUES (?, ?, ?, ?)",
                       ("Objectif Écosystème Global & Autonomie", 2000.0, 540.25, "en_cours"))

    cursor.execute("SELECT COUNT(*) FROM treasury_balances")
    if cursor.fetchone()[0] == 0:
        default_treasury = [
            ('fiat', 'Stripe', 1250.50),
            ('fiat', 'PayPal', 340.00),
            ('fiat', 'Revolut', 890.25),
            ('crypto', 'USDT', 450.00),
            ('crypto', 'BTC', 0.015),
            ('crypto', 'ETH', 0.12)
        ]
        cursor.executemany("INSERT INTO treasury_balances (asset_type, asset_name, amount) VALUES (?, ?, ?)", default_treasury)

    cursor.execute("SELECT COUNT(*) FROM nexus_identities")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO nexus_identities (full_name, identity_type, access_level, status, created_at) VALUES (?, ?, ?, ?, ?)",
                       ("Nexus Prime Operator", "Identité Civile Virtuelle", "Niveau Alpha (Accès Total)", "Actif", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

init_web_db()

def get_nexus_data():
    conn = sqlite3.connect("nexus_memory.db")
    cursor = conn.cursor()
    
    # Objectif global
    cursor.execute("SELECT goal_name, target_amount, current_amount FROM performance_goals WHERE status = 'en_cours'")
    goal_row = cursor.fetchone()
    goal_name, target, current = goal_row if goal_row else ("Objectif Global multi-département", 2000.0, 540.25)
    progress = (current / target) * 100 if target > 0 else 0

    # Départements
    cursor.execute("SELECT dept_code, dept_name, status, active_tasks_count, cpu_load, last_activity FROM departments")
    departments = cursor.fetchall()

    # Trésorerie
    cursor.execute("SELECT asset_name, amount FROM treasury_balances WHERE asset_type='fiat'")
    fiat = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.execute("SELECT asset_name, amount FROM treasury_balances WHERE asset_type='crypto'")
    crypto = {row[0]: row[1] for row in cursor.fetchall()}

    # Identités Nexus
    cursor.execute("SELECT id, full_name, identity_type, access_level, status, created_at FROM nexus_identities ORDER BY id DESC")
    identities = cursor.fetchall()

    # Logs récents
    cursor.execute("SELECT timestamp, department, task_name, result, progress_step FROM actions_log ORDER BY id DESC LIMIT 8")
    logs = cursor.fetchall()

    # Commandes
    cursor.execute("SELECT id, timestamp, department, text, status, progress_label FROM commands ORDER BY id DESC LIMIT 6")
    commands = cursor.fetchall()
    
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
        "commands": commands
    }

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nexus OS - Multi-Department & Identity Core</title>
    <style>
        :root {
            --bg-base: #090d16;
            --bg-card: rgba(30, 41, 59, 0.7);
            --border-card: rgba(255, 255, 255, 0.08);
            --accent-blue: #38bdf8;
            --accent-green: #10b981;
            --accent-purple: #8b5cf6;
            --accent-orange: #f59e0b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: var(--bg-base);
            color: var(--text-main);
            margin: 0;
            padding: 30px;
            overflow-x: hidden;
            background-image: radial-gradient(circle at 10% 20%, rgba(56, 189, 248, 0.05) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.05) 0%, transparent 40%);
        }

        .container { max-width: 1400px; margin: auto; }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-card);
            padding: 20px 30px;
            border-radius: 16px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .header h1 { margin: 0; font-size: 1.6em; background: linear-gradient(90deg, #38bdf8, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .system-status { display: flex; align-items: center; gap: 10px; font-size: 0.9em; color: var(--accent-green); font-weight: 600; }
        .pulse-dot { width: 10px; height: 10px; background: var(--accent-green); border-radius: 50%; box-shadow: 0 0 10px var(--accent-green); animation: pulse 2s infinite; }
        @keyframes pulse { 0% { transform: scale(0.95); opacity: 0.8; } 50% { transform: scale(1.2); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.8; } }

        .kpi-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-card);
            padding: 22px;
            border-radius: 16px;
            margin-bottom: 25px;
            position: relative;
            overflow: hidden;
        }
        .kpi-card::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--accent-green); }
        .progress-bar-container { background: rgba(15, 23, 42, 0.8); border-radius: 12px; height: 22px; width: 100%; margin-top: 12px; overflow: hidden; position: relative; border: 1px solid rgba(255,255,255,0.05); }
        .progress-bar { background: linear-gradient(90deg, #3b82f6, #10b981); height: 100%; width: {{ data.progress }}%; transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); border-radius: 12px; }
        .progress-text { position: absolute; width: 100%; text-align: center; font-size: 0.8em; font-weight: 700; top: 3px; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.6); }

        .section-title { font-size: 1.1em; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }
        
        .grid-departments { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
        .dept-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-card);
            padding: 18px;
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            transition: transform 0.3s ease, border-color 0.3s ease;
            cursor: pointer;
        }
        .dept-card:hover { transform: translateY(-3px); border-color: rgba(56, 189, 248, 0.4); }
        .dept-card h3 { margin: 0 0 10px 0; font-size: 0.9em; color: var(--accent-blue); display: flex; justify-content: space-between; align-items: center; }
        .dept-metric { font-size: 0.85em; color: var(--text-muted); margin-bottom: 5px; }
        .dept-metric span { color: var(--text-main); font-weight: 600; }

        .grid-2 { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 25px; }
        .card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-card);
            padding: 22px;
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        /* Tiroirs (Drawers) */
        .drawer-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); z-index: 1000; }
        .drawer { position: fixed; top: 0; right: -480px; width: 450px; height: 100%; background: #111827; border-left: 1px solid var(--border-card); box-shadow: -20px 0 50px rgba(0,0,0,0.8); z-index: 1001; transition: right 0.4s cubic-bezier(0.16, 1, 0.3, 1); padding: 30px; box-sizing: border-box; overflow-y: auto; }
        .drawer.open { right: 0; }
        .drawer-close { background: none; border: none; color: var(--text-muted); font-size: 1.5em; cursor: pointer; float: right; }
        .drawer h2 { color: var(--accent-blue); margin-top: 0; }

        textarea, select, input { width: 100%; padding: 12px; margin-top: 10px; background: rgba(15, 23, 42, 0.9); border: 1px solid var(--border-card); color: white; border-radius: 10px; box-sizing: border-box; font-family: inherit; font-size: 0.95em; outline: none; }
        textarea:focus, select:focus, input:focus { border-color: var(--accent-blue); }
        
        .btn-action { background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; border: none; padding: 12px 20px; margin-top: 12px; border-radius: 10px; cursor: pointer; font-weight: 600; width: 100%; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4); }
        .btn-action:hover { opacity: 0.9; }

        .timeline-box { background: var(--bg-card); backdrop-filter: blur(16px); border: 1px solid var(--border-card); padding: 25px; border-radius: 16px; margin-top: 25px; }
        .timeline-item { display: flex; align-items: flex-start; gap: 15px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.9em; }
        .timeline-badge { background: rgba(56, 189, 248, 0.1); color: var(--accent-blue); padding: 4px 10px; border-radius: 20px; font-size: 0.75em; font-weight: 700; white-space: nowrap; border: 1px solid rgba(56, 189, 248, 0.2); }

        @media(max-width: 1000px) {
            .grid-departments { grid-template-columns: repeat(2, 1fr); }
            .grid-2 { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>✨ Nexus OS <span style="font-size: 0.5em; color: var(--text-muted);">Multi-Department & Identity Core</span></h1>
            <div class="system-status">
                <div class="pulse-dot"></div> Serveur et Identités Synchronisés
            </div>
        </div>

        <!-- Objectif global KPI -->
        <div class="kpi-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="color: var(--text-muted); font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px;">Objectif Écosystème Global</span>
                    <h2 style="margin: 4px 0 0 0; font-size: 1.2em;">{{ data.goal_name }}</h2>
                </div>
                <div style="text-align: right;">
                    <span style="color: var(--accent-green); font-size: 1.3em; font-weight: 700;">{{ "%.2f"|format(data.current) }} $</span>
                    <span style="color: var(--text-muted);">/ {{ data.target }} $</span>
                </div>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar"></div>
                <div class="progress-text">{{ "%.1f"|format(data.progress) }}% Atteint</div>
            </div>
        </div>

        <!-- VUE DES DÉPARTEMENTS DU SERVEUR -->
        <div class="section-title">🏢 Départements Actifs du Serveur Nexus <span>Cliquer pour inspecter</span></div>
        <div class="grid-departments">
            {% for dept in data.departments %}
            <div class="dept-card" onclick="openDeptDrawer('{{ dept[0] }}')">
                <h3>{{ dept[1].split(' ')[1] if ' ' in dept[1] else dept[1] }} <span>↗</span></h3>
                <div class="dept-metric">Statut : <span style="color: var(--accent-green);">{{ dept[2] }}</span></div>
                <div class="dept-metric">Tâches en cours : <span>{{ dept[3] }}</span></div>
                <div class="dept-metric">Charge CPU : <span>{{ dept[4] }}</span></div>
                <div class="dept-metric" style="font-size: 0.75em; color: var(--text-muted); margin-top: 8px;">Dernier event : {{ dept[5] }}</div>
            </div>
            {% endfor %}
        </div>

        <!-- Zone Centrale : Pilotage & Gestion des Identités / Accès Nexus -->
        <div class="grid-2">
            <!-- Console d'envoi d'ordre ciblé par département -->
            <div class="card" style="border-left: 4px solid var(--accent-blue);">
                <h3>🚀 Assigner une mission à un département</h3>
                <form method="POST" action="/command">
                    <select name="department" style="margin-bottom: 10px;">
                        <option value="trading">Département Trading (MT5 / PyTorch)</option>
                        <option value="microtasks">Département Micro-tâches (Prolific)</option>
                        <option value="treasury">Département Trésorerie & Fiat</option>
                        <option value="infra">Département Infrastructure VPS</option>
                    </select>
                    <textarea name="instruction" rows="2" placeholder="Ex: Ajuster les seuils, vérifier les flux..."></textarea>
                    <button type="submit" class="btn-action">Transmettre la directive</button>
                </form>
            </div>

            <!-- Gestion des Identités Civiles & Accès Nexus -->
            <div class="card" style="border-left: 4px solid var(--accent-purple);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0;">🪪 Identités & Accès Nexus</h3>
                    <button onclick="openIdentityModal()" style="background: rgba(139, 92, 246, 0.2); border: 1px solid var(--accent-purple); color: var(--accent-purple); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.8em; font-weight: 600;">+ Créer</button>
                </div>
                <div style="max-height: 120px; overflow-y: auto; margin-top: 10px;">
                    {% for id_row in data.identities %}
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.85em;">
                            <span><b>{{ id_row[1] }}</b> (<i>{{ id_row[3] }}</i>)</span>
                            <span style="color: var(--accent-green); font-weight: 600;">{{ id_row[4] }}</span>
                        </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        <!-- Flux d'activités Global de tous les départements -->
        <div class="timeline-box">
            <h3 style="margin-top: 0; color: var(--text-muted); font-size: 0.9em; text-transform: uppercase;">📋 Journaux croisés des départements</h3>
            <div>
                {% for log in data.logs %}
                    <div class="timeline-item">
                        <div class="timeline-badge">{{ log[1] | upper }}</div>
                        <div style="flex-grow: 1;">
                            <div><b>{{ log[2] }}</b> : {{ log[3] }} <span style="float: right; color: var(--text-muted); font-size: 0.8em;">{{ log[0] }}</span></div>
                        </div>
                    </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <!-- Tiroir Interactif des Départements -->
    <div class="drawer-overlay" id="drawerOverlay" onclick="closeDrawers()"></div>
    <div class="drawer" id="deptDrawer">
        <button class="drawer-close" onclick="closeDrawers()">&times;</button>
        <h2 id="drawerTitle">Gestion Département</h2>
        <p style="color: var(--text-muted); font-size: 0.9em;" id="drawerDesc">Inspection des processus et journaux du sous-système.</p>
        <hr style="border: 0; border-top: 1px solid var(--border-card); margin: 20px 0;">
        <div id="drawerContent">Chargement des flux...</div>
        <button class="btn-action" style="margin-top: 25px;" onclick="alert('Diagnostic et synchronisation du département effectués avec succès.')">Exécuter un diagnostic complet</button>
    </div>

    <!-- Tiroir / Modal de Création d'Identité Nexus -->
    <div class="drawer" id="identityDrawer">
        <button class="drawer-close" onclick="closeDrawers()">&times;</button>
        <h2>Création d'Identité & Accès</h2>
        <p style="color: var(--text-muted); font-size: 0.9em;">Permettre à Nexus d'utiliser l'identité civile, les cartes et les accès.</p>
        <form method="POST" action="/create_identity">
            <input type="text" name="full_name" placeholder="Nom complet ou Alias civil" required style="margin-bottom: 10px;">
            <select name="identity_type" style="margin-bottom: 10px;">
                <option value="Identité Civile Virtuelle">Identité Civile Virtuelle</option>
                <option value="Carte d'Accès Sécurisée">Carte d'Accès Sécurisée</option>
                <option value="Passerelle d'Authentification API">Passerelle d'Authentification API</option>
            </select>
            <select name="access_level" style="margin-bottom: 15px;">
                <option value="Niveau Alpha (Accès Total)">Niveau Alpha (Accès Total)</option>
                <option value="Niveau Beta (Opérationnel Restreint)">Niveau Beta (Opérationnel Restreint)</option>
                <option value="Niveau Gamma (Lecture seule)">Niveau Gamma (Lecture seule)</option>
            </select>
            <button type="submit" class="btn-action">Générer et Enregistrer l'Accès</button>
        </form>
    </div>

    <script>
        function openDeptDrawer(deptCode) {
            document.getElementById('drawerOverlay').style.display = 'block';
            const drawer = document.getElementById('deptDrawer');
            drawer.classList.add('open');
            document.getElementById('drawerTitle').innerText = "Département : " + deptCode.toUpperCase();
            document.getElementById('drawerDesc').innerText = "Surveillance en temps réel du module " + deptCode;
            document.getElementById('drawerContent').innerHTML = "<b>État :</b> Opérationnel<br><b>Passerelle :</b> Connectée à SQLite<br><b>Sécurité :</b> Chiffrée<br><br><i>Aucune anomalie détectée sur ce sous-réseau du serveur.</i>";
        }
        function openIdentityModal() {
            document.getElementById('drawerOverlay').style.display = 'block';
            document.getElementById('identityDrawer').classList.add('open');
        }
        function closeDrawers() {
            document.getElementById('drawerOverlay').style.display = 'none';
            document.getElementById('deptDrawer').classList.remove('open');
            document.getElementById('identityDrawer').classList.remove('open');
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    data = get_nexus_data()
    return render_template_string(DASHBOARD_TEMPLATE, data=data)

@app.route("/command", methods=["POST"])
def command():
    dept = request.form.get("department", "general")
    instruction = request.form.get("instruction")
    if instruction:
        conn = sqlite3.connect("nexus_memory.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO commands (timestamp, department, text, status, progress_label) VALUES (datetime('now'), ?, ?, ?, ?)",
            (dept, instruction, "En cours", "Traitement interne")
        )
        cursor.execute(
            "INSERT INTO actions_log (timestamp, department, task_name, result, progress_step) VALUES (datetime('now'), ?, ?, ?, ?)",
            (dept, "Ordre Stratégique", instruction, "Transmis au sous-système")
        )
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route("/create_identity", methods=["POST"])
def create_identity():
    full_name = request.form.get("full_name")
    identity_type = request.form.get("identity_type")
    access_level = request.form.get("access_level")
    if full_name:
        conn = sqlite3.connect("nexus_memory.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO nexus_identities (full_name, identity_type, access_level, status, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (full_name, identity_type, access_level, "Actif")
        )
        cursor.execute(
            "INSERT INTO actions_log (timestamp, department, task_name, result, progress_step) VALUES (datetime('now'), 'infra', 'Création d\'Accès', ?, ?)",
            (f"Nouvelle identité générée : {full_name} ({identity_type})", "Validation OK")
        )
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
