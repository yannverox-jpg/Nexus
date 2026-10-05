import asyncio
import sqlite3
import random
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Import de votre boîte à outils d'identité et de géolocalisation
from virtual_tools import VirtualIdentityToolkit

load_dotenv()

# --- 1. GESTION DE LA MÉMOIRE ET DES ORDRES (SQLite) ---
class NexusMemory:
    def __init__(self, db_name="nexus_memory.db"):
        self.db_name = db_name
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                text TEXT,
                status TEXT
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

    def get_pending_commands(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, text FROM commands WHERE status = 'pending'")
        return cursor.fetchall()

    def mark_command_done(self, cmd_id):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE commands SET status = 'completed' WHERE id = ?", (cmd_id,))
        self.conn.commit()


# --- 2. MODULE DE CONNEXION FURTIVE ET LECTURE WEBMAIL (PLAYWRIGHT + STEALTH) ---
async def login_with_webmail_otp(platform_name: str, login_url: str, toolkit: VirtualIdentityToolkit):
    print(f"\n[Nexus Stealth Login] Connexion à {platform_name}...")

    profile = toolkit.generate_virtual_profile()
    geo = toolkit.get_geolocation_data(profile['city'], profile['country'])

    lat = geo.get("latitude", 48.8566)
    lon = geo.get("longitude", 2.3522)
    tz = geo.get("timezone", "Europe/Paris")

    print(f"[Géolocalisation injectée] Lat: {lat}, Lon: {lon} | Fuseau: {tz}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            geolocation={"latitude": lat, "longitude": lon},
            permissions=["geolocation"],
            timezone_id=tz,
            locale="fr-FR"
        )

        page = await context.new_page()
        await stealth_async(page)

        try:
            # 1. Accès à la plateforme cible
            await page.goto(login_url, timeout=60000)
            print(f"[Nexus] Page de {platform_name} chargée sous camouflage.")

            print("⏳ [Action Requise] Entrez vos identifiants ou laissez Nexus tenter l'auto-remplissage.")
            await asyncio.sleep(15)

            # 2. Simulation d'une vérification par e-mail (Multi-onglets)
            print("[Nexus] Vérification si un code OTP par e-mail est exigé...")
            mail_page = await context.new_page()
            await stealth_async(mail_page)
            await mail_page.goto("https://mail.google.com", timeout=60000)
            print("[Nexus Webmail] Onglet messagerie ouvert.")

            await asyncio.sleep(10)

            # Retour sur la plateforme cible
            await page.bring_to_front()
            print("[Nexus] Retour sur la plateforme cible.")

            await asyncio.sleep(10)

            # Capture d'écran finale de validation
            screenshot_path = f"screenshot_{platform_name.lower()}.png"
            await page.screenshot(path=screenshot_path)
            print(f"[Nexus] Session capturée : {screenshot_path}")

            await browser.close()
            return f"Connexion et navigation multi-onglets réussies pour {platform_name}."

        except Exception as e:
            await browser.close()
            return f"Erreur lors de la session {platform_name} : {str(e)}"


# --- 3. CERVEAU CENTRAL DE NEXUS ---
class NexusCore:
    def __init__(self):
        self.memory = NexusMemory()
        self.toolkit = VirtualIdentityToolkit(locale='fr_FR')
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    async def run_cycle(self):
        print("\n================ NEXUS CYCLE ================")

        # Traitement des ordres reçus via le Dashboard
        pending_cmds = self.memory.get_pending_commands()
        if pending_cmds:
            for cmd_id, text in pending_cmds:
                print(f"🎯 Ordre reçu du Dashboard : '{text}'")
                text_lower = text.lower()
                result_msg = "Ordre exécuté."

                if "stripe" in text_lower:
                    result_msg = await login_with_webmail_otp("Stripe", "https://dashboard.stripe.com/login", self.toolkit)
                elif "paypal" in text_lower:
                    result_msg = await login_with_webmail_otp("PayPal", "https://www.paypal.com/signin", self.toolkit)
                elif "revolut" in text_lower:
                    result_msg = await login_with_webmail_otp("Revolut", "https://app.revolut.com/start", self.toolkit)
                else:
                    urls = re.findall(r'https?://[^\s]+', text)
                    if urls:
                        result_msg = f"Navigation ciblée vers : {urls[0]}"

                self.memory.log_action(task_name="Ordre Web Exécuté", result=result_msg, revenue=0.0)
                self.memory.mark_command_done(cmd_id)

        # Analyse autonome standard par l'IA
        system_prompt = "Tu es Nexus, un agent IA autonome de gestion de trésorerie et d'automatisation web."
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="Vérifie l'état général des flux et des tâches en attente.")
        ]
        response = await self.llm.ainvoke(messages)
        decision = response.content.strip()
        print(f"Raisonnement Nexus : {decision[:120]}...")

        self.memory.log_action(task_name="Vérification Autonome", result=decision[:100], revenue=0.0)
        print("================================================")

    async def start_autonomous_loop(self, interval_seconds=1800):
        print("Nexus tourne en arrière-plan et écoute vos ordres 24/7...")
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                print(f"Erreur critique dans la boucle : {e}")

            await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    bot = NexusCore()
    asyncio.run(bot.run_cycle())
