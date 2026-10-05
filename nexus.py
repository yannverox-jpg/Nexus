import asyncio
import sqlite3
import random
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Import de votre boîte à outils virtuelle créée précédemment
from virtual_tools import VirtualIdentityToolkit

load_dotenv()

# --- 1. GESTION DE LA MÉMOIRE PERSISTANTE (SQLite) ---
class NexusMemory:
    def __init__(self, db_name="nexus_memory.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                task_name TEXT,
                result TEXT,
                revenue_generated REAL
            )
        ''')
        self.conn.commit()

    def log_action(self, task_name, result, revenue=0.0):
        cursor = self.conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO actions_log (timestamp, task_name, result, revenue_generated) VALUES (?, ?, ?, ?)",
            (timestamp, task_name, result, revenue)
        )
        self.conn.commit()

    def get_total_revenue(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(revenue_generated) FROM actions_log")
        total = cursor.fetchone()[0]
        return total if total else 0.0

    def get_recent_history(self, limit=5):
        cursor = self.conn.cursor()
        cursor.execute("SELECT timestamp, task_name, result, revenue_generated FROM actions_log ORDER BY id DESC LIMIT ?", (limit,))
        return cursor.fetchall()


# --- 2. NAVIGATION WEB INDÉTECTABLE (Anti-Cloudflare / Anti-Bot) ---
async def safe_stealth_browse(url: str, identity: dict) -> str:
    """Ouvre une page web en simulant un humain réel pour contourner les blocages."""
    print(f"[Stealth Browser] Connexion sécurisée vers : {url} sous l'identité de {identity['name']}")
    
    async with async_playwright() as p:
        # Lancement avec des arguments pour masquer le fait que c'est un bot automatisé
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080"
            ]
        )
        
        # Contexte simulant un utilisateur réel (langue, fuseau horaire, dimensions)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id=identity.get("timezone", "America/New_York")
        )
        
        page = await context.new_page()
        
        # Application du patch anti-détection majeur (Playwright Stealth)
        await stealth_async(page)

        try:
            # Navigation avec un délai d'attente large
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            
            # Pause humaine aléatoire (pour imiter la lecture)
            delay = random.uniform(2.5, 6.0)
            await asyncio.sleep(delay)
            
            # Simulation d'un petit mouvement de souris aléatoire
            await page.mouse.move(random.randint(100, 500), random.randint(100, 500))

            # Extraction du contenu textuel de la page
            content = await page.evaluate("document.body.innerText")
            await browser.close()
            return content[:3000] # Limité pour le traitement LLM
            
        except Exception as e:
            await browser.close()
            return f"Erreur de navigation sécurisée : {str(e)}"


# --- 3. CERVEAU AUTONOME DE NEXUS ---
class NexusCore:
    def __init__(self):
        self.memory = NexusMemory()
        # Initialisation de l'identité virtuelle de base (ex: profil US pour les plateformes globales)
        self.toolkit = VirtualIdentityToolkit(locale='en_US')
        self.current_identity = self.toolkit.generate_virtual_profile()
        
        # Récupération géolocalisée pour caler le fuseau horaire
        geo = self.toolkit.get_geolocation_data(self.current_identity['city'], self.current_identity['country'])
        if "timezone" in geo:
            self.current_identity['timezone'] = geo['timezone']
        else:
            self.current_identity['timezone'] = "America/New_York"

        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    async def run_cycle(self):
        print("\n================ N NEXUS CYCLE START ================")
        print(f"Identité active : {self.current_identity['name']} ({self.current_identity['city']}, {self.current_identity['country']})")
        
        history = self.memory.get_recent_history(limit=3)
        total_rev = self.memory.get_total_revenue()
        
        system_prompt = (
            "Tu es Nexus, un agent IA autonome spécialisé dans la recherche d'opportunités de revenus, "
            "le scraping éthique et l'affiliation en ligne. Analyse l'historique et choisis une action. "
            "Si tu as besoin de visiter une URL pour analyser un marché ou une page, réponds UNIQUEMENT "
            "au format de commande URL: https://exemple.com."
        )
        
        context_msg = f"Historique récent : {history}\nRevenu total généré : ${total_rev}\nQuelle est la prochaine étape stratégique ?"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context_msg)
        ]

        # Le LLM décide
        response = await self.llm.ainvoke(messages)
        decision = response.content.strip()
        print(f"Stratégie décidée par Nexus :\n{decision}")

        # Traitement de l'URL si demandée par l'IA via le navigateur stealth
        scraped_result = "Aucune navigation requise pour ce cycle."
        urls = re.findall(r'https?://[^\s]+', decision)
        if urls:
            target_url = urls[0].strip('.,')
            scraped_result = await safe_stealth_browse(target_url, self.current_identity)
            print(f"[Navigation réussie] Aperçu extrait : {scraped_result[:250]}...")

        # Enregistrement de l'action dans la base de données persistante
        self.memory.log_action(
            task_name="Cycle Autonome Intelligent",
            result=f"Décision: {decision[:100]} | Résultat web: {scraped_result[:100]}",
            revenue=0.0 # Sera mis à jour automatiquement lors des conversions réelles
        )
        print("Cycle enregistré dans la mémoire persistante SQLite.")
        print("=====================================================")

    async def start_24_7_loop(self, interval_seconds=3600):
        """Boucle infinie sécurisée pour tourner 24/7 sur un serveur cloud (Render)."""
        print("Nexus est officiellement en ligne et démarre sa surveillance 24/7...")
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                print(f"Erreur critique interceptée dans la boucle 24/7 : {e}")
            
            # Attente aléatoire avant le prochain cycle pour paraître encore plus naturel
            wait_time = interval_seconds + random.randint(-300, 300)
            print(prochaine_action := f"Mise en veille de Nexus pour {wait_time} secondes...\n")
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    bot = NexusCore()
    # Test d'un cycle immédiat en local
    asyncio.run(bot.run_cycle())
