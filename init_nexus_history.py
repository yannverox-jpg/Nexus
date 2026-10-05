import sqlite3

db_path = "nexus_memory.db"

def inject_initial_context():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # S'assurer que la table existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Historique initial de notre échange et de l'architecture Nexus
    initial_messages = [
        ("Gemini (Google)", "assistant", "Nexus OS initialisé. Je suis connecté à votre serveur Ubuntu. Toutes vos ingénieries, modules (ghost.py, web.py, main.py) et la base de données SQLite sont en place."),
        ("Gemini (Google)", "user", "Rappelle-moi la vision globale de Nexus."),
        ("Gemini (Google)", "assistant", "Nexus est votre Command Center centralisé sur Ubuntu/WSL. Il sert d'OS unifié pour superviser, lancer et surveiller vos scripts d'automatisation locale et vos fenêtres réelles (via playwright-stealth en mode headless=False). Le dashboard Streamlit (port 8501) indexe dynamiquement vos projets (Ghost, web.py, etc.) et synchronise vos conversations IA en persistance SQLite."),
        ("Gemini (Google)", "user", "Parfait. Veveille à ce que chaque échange et chaque brique technique reste accessible et persisté dans le dashboard.")
    ]

    # Insertion en base de données pour le modèle Gemini (et optionnellement les autres)
    for model, role, content in initial_messages:
        cursor.execute(
            "INSERT INTO chat_history (model_name, role, content) VALUES (?, ?, ?)",
            (model, role, content)
        )

    conn.commit()
    conn.close()
    print("✅ Contexte initial de Nexus injecté avec succès dans SQLite !")

if __name__ == "__main__":
    inject_initial_context()
