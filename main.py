```python
import asyncio
import sqlite3
import random
import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Import de votre boîte à outils d'identité et de géolocalisation
from virtual_tools import VirtualIdentityToolkit

load_dotenv()


# ============================================================
# 1. OUTILS RUNTIME
# ============================================================

def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def safe_json(value):
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return json.dumps(str(value), ensure_ascii=False)


# ============================================================
# 2. GESTION DE LA MÉMOIRE ET DU RUNTIME SQLITE
# ============================================================

class NexusMemory:

    def __init__(self, db_name="nexus_memory.db"):
        self.db_name = db_name

        self.conn = sqlite3.connect(
            db_name,
            timeout=30,
            check_same_thread=False
        )

        self.conn.row_factory = sqlite3.Row

        self._configure_database()
        self.create_tables()

    def _configure_database(self):
        cursor = self.conn.cursor()

        # Permet au dashboard et au moteur de travailler simultanément.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")

        self.conn.commit()

    def _table_columns(self, table_name):
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in cursor.fetchall()}

    def _add_column_if_missing(self, table_name, column_name, definition):
        columns = self._table_columns(table_name)

        if column_name not in columns:
            cursor = self.conn.cursor()
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )
            self.conn.commit()

    def create_tables(self):
        cursor = self.conn.cursor()

        # --------------------------------------------------------
        # actions_log
        # --------------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                task_name TEXT,
                result TEXT,
                revenue_generated REAL
            )
        """)

        # Compatibilité avec les anciennes versions du dashboard/web.
        self._add_column_if_missing(
            "actions_log",
            "department",
            "TEXT"
        )

        self._add_column_if_missing(
            "actions_log",
            "progress_step",
            "TEXT"
        )

        # --------------------------------------------------------
        # commands
        # --------------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                text TEXT,
                status TEXT
            )
        """)

        # Compatibilité avec nexus_web.py.
        self._add_column_if_missing(
            "commands",
            "department",
            "TEXT"
        )

        self._add_column_if_missing(
            "commands",
            "progress_label",
            "TEXT"
        )

        # --------------------------------------------------------
        # nexus_events
        # --------------------------------------------------------

        cursor.execute("""
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
        """)

        # --------------------------------------------------------
        # nexus_agents
        # --------------------------------------------------------

        cursor.execute("""
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
        """)

        # --------------------------------------------------------
        # nexus_opportunities
        # --------------------------------------------------------

        cursor.execute("""
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
        """)

        self.conn.commit()

    # ========================================================
    # ACTIONS
    # ========================================================

    def log_action(
        self,
        task_name,
        result,
        revenue=0.0,
        department=None,
        progress_step=None
    ):
        cursor = self.conn.cursor()

        timestamp = now_iso()

        cursor.execute("""
            INSERT INTO actions_log
            (
                timestamp,
                task_name,
                result,
                revenue_generated,
                department,
                progress_step
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            task_name,
            result,
            revenue,
            department,
            progress_step
        ))

        self.conn.commit()

    # ========================================================
    # COMMANDES
    # ========================================================

    def get_pending_commands(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT id, text
            FROM commands
            WHERE status = 'pending'
            ORDER BY id ASC
        """)

        return cursor.fetchall()

    def mark_command_running(self, cmd_id, progress_label=None):
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE commands
            SET
                status = 'running',
                progress_label = ?
            WHERE id = ?
        """, (
            progress_label,
            cmd_id
        ))

        self.conn.commit()

    def mark_command_done(self, cmd_id):
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE commands
            SET
                status = 'completed',
                progress_label = 'Terminé'
            WHERE id = ?
        """, (cmd_id,))

        self.conn.commit()

    def mark_command_error(self, cmd_id, error_message):
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE commands
            SET
                status = 'error',
                progress_label = ?
            WHERE id = ?
        """, (
            str(error_message)[:500],
            cmd_id
        ))

        self.conn.commit()

    # ========================================================
    # EVENEMENTS RUNTIME
    # ========================================================

    def record_event(
        self,
        event_type,
        agent,
        step,
        status,
        action=None,
        target=None,
        details=None,
        result=None,
        url=None,
        metadata=None
    ):
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO nexus_events
            (
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
        """, (
            now_iso(),
            event_type,
            agent,
            step,
            status,
            action,
            target,
            details,
            result,
            url,
            safe_json(metadata or {})
        ))

        self.conn.commit()

    # ========================================================
    # ETAT D'AGENT
    # ========================================================

    def update_agent(
        self,
        agent_name,
        role,
        status,
        current_step=None,
        current_task=None,
        metadata=None
    ):
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO nexus_agents
            (
                agent_name,
                role,
                status,
                current_step,
                current_task,
                last_activity,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_name)
            DO UPDATE SET
                role = excluded.role,
                status = excluded.status,
                current_step = excluded.current_step,
                current_task = excluded.current_task,
                last_activity = excluded.last_activity,
                metadata = excluded.metadata
        """, (
            agent_name,
            role,
            status,
            current_step,
            current_task,
            now_iso(),
            safe_json(metadata or {})
        ))

        self.conn.commit()

    # ========================================================
    # CONTEXTE POUR L'IA
    # ========================================================

    def get_recent_events(self, limit=30):
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                timestamp,
                event_type,
                agent,
                step,
                status,
                action,
                target,
                details,
                result,
                url
            FROM nexus_events
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def get_recent_actions(self, limit=20):
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                timestamp,
                task_name,
                result,
                revenue_generated,
                department,
                progress_step
            FROM actions_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def get_runtime_context(self):
        return {
            "mission": "détecter, évaluer et développer des opportunités de revenus légales et durables",
            "recent_events": self.get_recent_events(30),
            "recent_actions": self.get_recent_actions(20),
            "pending_commands": [
                {
                    "id": row["id"],
                    "text": row["text"]
                }
                for row in self.get_pending_commands()
            ]
        }


# ============================================================
# 3. NAVIGATION WEB EXISTANTE
# ============================================================

async def login_with_webmail_otp(
    platform_name: str,
    login_url: str,
    toolkit: VirtualIdentityToolkit,
    memory=None
):
    """
    Fonction de navigation existante.
    La télémétrie est ajoutée sans transformer cette fonction
    en générateur d'activité fictive.
    """

    def event(
        event_type,
        step,
        status,
        action=None,
        details=None,
        result=None,
        url=None
    ):
        if memory:
            memory.record_event(
                event_type=event_type,
                agent="web_operator",
                step=step,
                status=status,
                action=action,
                target=platform_name,
                details=details,
                result=result,
                url=url
            )

    print(
        f"\n[Nexus Web] Connexion à {platform_name}..."
    )

    event(
        "WEB_ACTIVITY",
        "OBSERVE",
        "started",
        action="Préparation de la navigation",
        details=f"Préparation de la session pour {platform_name}",
        url=login_url
    )

    profile = toolkit.generate_virtual_profile()

    # Correction du bug existant :
    # get_geolocation_data() reçoit une seule chaîne.
    address = f"{profile['city']}, {profile['country']}"

    geo = toolkit.get_geolocation_data(address)

    lat = geo.get("latitude", 48.8566)
    lon = geo.get("longitude", 2.3522)
    tz = geo.get("timezone", "Europe/Paris")

    print(
        f"[Géolocalisation] Lat: {lat}, Lon: {lon} | Fuseau: {tz}"
    )

    event(
        "WEB_ACTIVITY",
        "OBSERVE",
        "completed",
        action="Préparation du contexte navigateur",
        details=f"Contexte géographique préparé pour {platform_name}",
        result=f"timezone={tz}",
        url=login_url
    )

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
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={
                "width": 1920,
                "height": 1080
            },
            geolocation={
                "latitude": lat,
                "longitude": lon
            },
            permissions=["geolocation"],
            timezone_id=tz,
            locale="fr-FR"
        )

        page = await context.new_page()
        await stealth_async(page)

        try:

            # ------------------------------------------------
            # OBSERVE
            # ------------------------------------------------

            event(
                "WEB_ACTIVITY",
                "OBSERVE",
                "running",
                action="Ouverture de la page cible",
                details=f"Navigation vers {platform_name}",
                url=login_url
            )

            await page.goto(
                login_url,
                timeout=60000,
                wait_until="domcontentloaded"
            )

            print(
                f"[Nexus] Page de {platform_name} chargée."
            )

            event(
                "WEB_ACTIVITY",
                "OBSERVE",
                "completed",
                action="Page cible chargée",
                details=f"{platform_name} accessible",
                url=page.url
            )

            # ------------------------------------------------
            # ETAT DE LA PAGE
            # ------------------------------------------------

            title = await page.title()

            body_text = ""

            try:
                body_text = await page.locator("body").inner_text(
                    timeout=10000
                )
            except Exception:
                pass

            page_excerpt = body_text[:3000]

            event(
                "WEB_ACTIVITY",
                "RESEARCH",
                "completed",
                action="Lecture du contenu de la page",
                details=page_excerpt,
                result=f"Titre: {title}",
                url=page.url
            )

            print(
                f"[Nexus] Page analysée : {title}"
            )

            # ------------------------------------------------
            # ATTENTE INTERACTION
            # ------------------------------------------------

            event(
                "WEB_ACTIVITY",
                "EXECUTE",
                "waiting",
                action="Attente d'une éventuelle intervention utilisateur",
                details=(
                    "La session reste ouverte conformément au "
                    "comportement existant."
                ),
                url=page.url
            )

            print(
                "⏳ [Action Requise] Session ouverte pour intervention."
            )

            await asyncio.sleep(15)

            # ------------------------------------------------
            # WEBMAIL
            # ------------------------------------------------

            event(
                "WEB_ACTIVITY",
                "OBSERVE",
                "running",
                action="Ouverture de la messagerie",
                target="Gmail",
                url="https://mail.google.com"
            )

            mail_page = await context.new_page()
            await stealth_async(mail_page)

            await mail_page.goto(
                "https://mail.google.com",
                timeout=60000,
                wait_until="domcontentloaded"
            )

            print(
                "[Nexus Webmail] Onglet messagerie ouvert."
            )

            event(
                "WEB_ACTIVITY",
                "OBSERVE",
                "completed",
                action="Messagerie ouverte",
                target="Gmail",
                url=mail_page.url
            )

            await asyncio.sleep(10)

            await page.bring_to_front()

            event(
                "WEB_ACTIVITY",
                "EXECUTE",
                "completed",
                action="Retour sur la plateforme cible",
                target=platform_name,
                url=page.url
            )

            await asyncio.sleep(10)

            # ------------------------------------------------
            # CAPTURE
            # ------------------------------------------------

            screenshot_path = (
                f"screenshot_{platform_name.lower()}.png"
            )

            await page.screenshot(
                path=screenshot_path
            )

            print(
                f"[Nexus] Session capturée : {screenshot_path}"
            )

            result = (
                f"Navigation et observation terminées pour "
                f"{platform_name}."
            )

            event(
                "WEB_ACTIVITY",
                "VERIFY",
                "completed",
                action="Capture de validation",
                target=platform_name,
                details=screenshot_path,
                result=result,
                url=page.url
            )

            await browser.close()

            return result

        except Exception as e:

            error_message = str(e)

            event(
                "WEB_ACTIVITY",
                "VERIFY",
                "error",
                action="Erreur durant la session web",
                target=platform_name,
                details=error_message,
                result="Session interrompue",
                url=getattr(page, "url", login_url)
            )

            try:
                await browser.close()
            except Exception:
                pass

            return (
                f"Erreur lors de la session "
                f"{platform_name} : {error_message}"
            )


# ============================================================
# 4. CERVEAU CENTRAL DE NEXUS
# ============================================================

class NexusCore:

    def __init__(self):

        self.memory = NexusMemory()

        self.toolkit = VirtualIdentityToolkit(
            locale="fr_FR"
        )

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3
        )

        self.agent_name = "nexus_core"

        self.memory.update_agent(
            agent_name=self.agent_name,
            role="centre de commandement autonome",
            status="idle",
            current_step="WAITING",
            current_task="En attente d'activité"
        )

    # ========================================================
    # EVENEMENT SIMPLIFIE
    # ========================================================

    def event(
        self,
        step,
        status,
        action=None,
        details=None,
        result=None,
        target=None,
        url=None,
        event_type="NEXUS_PIPELINE"
    ):
        self.memory.record_event(
            event_type=event_type,
            agent=self.agent_name,
            step=step,
            status=status,
            action=action,
            target=target,
            details=details,
            result=result,
            url=url
        )

        self.memory.update_agent(
            agent_name=self.agent_name,
            role="centre de commandement autonome",
            status=status,
            current_step=step,
            current_task=action,
            metadata={
                "target": target,
                "url": url
            }
        )

    # ========================================================
    # TRAITEMENT D'UNE COMMANDE
    # ========================================================

    async def process_command(self, cmd_id, text):

        self.memory.mark_command_running(
            cmd_id,
            "Analyse de la commande"
        )

        self.event(
            "DISCOVER",
            "running",
            action="Analyse d'une commande utilisateur",
            details=text,
            target="Dashboard"
        )

        print(
            f"🎯 Ordre reçu du Dashboard : '{text}'"
        )

        text_lower = text.lower()

        result_msg = "Ordre analysé."

        try:

            # ------------------------------------------------
            # PLATEFORMES EXISTANTES
            # ------------------------------------------------

            if "stripe" in text_lower:

                self.event(
                    "EXECUTE",
                    "running",
                    action="Traitement de la cible Stripe",
                    target="Stripe"
                )

                result_msg = await login_with_webmail_otp(
                    "Stripe",
                    "https://dashboard.stripe.com/login",
                    self.toolkit,
                    self.memory
                )

            elif "paypal" in text_lower:

                self.event(
                    "EXECUTE",
                    "running",
                    action="Traitement de la cible PayPal",
                    target="PayPal"
                )

                result_msg = await login_with_webmail_otp(
                    "PayPal",
                    "https://www.paypal.com/signin",
                    self.toolkit,
                    self.memory
                )

            elif "revolut" in text_lower:

                self.event(
                    "EXECUTE",
                    "running",
                    action="Traitement de la cible Revolut",
                    target="Revolut"
                )

                result_msg = await login_with_webmail_otp(
                    "Revolut",
                    "https://app.revolut.com/start",
                    self.toolkit,
                    self.memory
                )

            else:

                # ------------------------------------------------
                # NAVIGATION CIBLEE EXISTANTE
                # ------------------------------------------------

                urls = re.findall(
                    r'https?://[^\s]+',
                    text
                )

                if urls:

                    target_url = urls[0].rstrip(".,);]")

                    self.event(
                        "RESEARCH",
                        "running",
                        action="Navigation ciblée",
                        details="URL détectée dans la commande",
                        target=target_url,
                        url=target_url
                    )

                    result_msg = (
                        f"Navigation ciblée vers : "
                        f"{target_url}"
                    )

                    self.event(
                        "RESEARCH",
                        "completed",
                        action="Cible web identifiée",
                        result=result_msg,
                        target=target_url,
                        url=target_url
                    )

                else:

                    self.event(
                        "EVALUATE",
                        "completed",
                        action="Commande reçue sans cible web directe",
                        details=text,
                        result="Commande transmise au centre de raisonnement"
                    )

                    result_msg = (
                        "Commande reçue et transmise au "
                        "centre de raisonnement."
                    )

            self.memory.log_action(
                task_name="Ordre Web Exécuté",
                result=result_msg,
                revenue=0.0,
                department="core",
                progress_step="EXECUTE"
            )

            self.memory.mark_command_done(cmd_id)

            self.event(
                "VERIFY",
                "completed",
                action="Vérification de la commande",
                result=result_msg,
                target="Dashboard"
            )

        except Exception as e:

            error_message = str(e)

            self.memory.mark_command_error(
                cmd_id,
                error_message
            )

            self.event(
                "VERIFY",
                "error",
                action="Échec de traitement de la commande",
                details=error_message,
                result="Commande interrompue",
                target="Dashboard"
            )

            self.memory.log_action(
                task_name="Erreur commande",
                result=error_message,
                revenue=0.0,
                department="core",
                progress_step="ERROR"
            )

    # ========================================================
    # CYCLE AUTONOME
    # ========================================================

    async def run_cycle(self):

        print(
            "\n================ NEXUS CYCLE ================"
        )

        self.event(
            "OBSERVE",
            "running",
            action="Démarrage d'un cycle Nexus",
            details="Recherche de commandes et état du runtime"
        )

        # ====================================================
        # 1. COMMANDES DU DASHBOARD
        # ====================================================

        pending_cmds = self.memory.get_pending_commands()

        if pending_cmds:

            self.event(
                "DISCOVER",
                "completed",
                action="Commandes en attente détectées",
                details=f"{len(pending_cmds)} commande(s)"
            )

            for cmd in pending_cmds:

                cmd_id = cmd["id"]
                text = cmd["text"]

                await self.process_command(
                    cmd_id,
                    text
                )

        else:

            self.event(
                "DISCOVER",
                "completed",
                action="Recherche des commandes",
                details="Aucune commande en attente"
            )

        # ====================================================
        # 2. CONTEXTE RÉEL DU RUNTIME
        # ====================================================

        self.event(
            "OBSERVE",
            "running",
            action="Construction du contexte Nexus"
        )

        runtime_context = (
            self.memory.get_runtime_context()
        )

        self.event(
            "OBSERVE",
            "completed",
            action="Contexte runtime construit",
            details=(
                f"{len(runtime_context['recent_events'])} événements récents, "
                f"{len(runtime_context['recent_actions'])} actions récentes"
            )
        )

        # ====================================================
        # 3. CONSULTATION IA
        # ====================================================

        self.event(
            "AI_CONSULT",
            "running",
            action="Consultation du modèle IA",
            details="Analyse du contexte réel de Nexus"
        )

        system_prompt = """
Tu es le centre de raisonnement de Nexus.

Mission principale :
détecter, évaluer et développer des opportunités de
revenus légales et durables.

Tu dois raisonner à partir de l'état réel fourni par Nexus.

Tu ne dois jamais prétendre qu'une action a été exécutée
si elle n'apparaît pas dans les événements ou résultats
fournis.

Tu dois distinguer :
- ce qui a été observé ;
- ce qui a été décidé ;
- ce qui a réellement été exécuté ;
- ce qui reste à vérifier.

Contraintes :
- respecter les règles des plateformes ;
- respecter les lois applicables ;
- protéger les identifiants et données privées ;
- ne pas inventer de résultats financiers ;
- signaler les actions nécessitant une validation humaine ;
- privilégier les actions vérifiables et mesurables.

Retourne une analyse courte et structurée.
"""

        context_text = json.dumps(
            runtime_context,
            ensure_ascii=False,
            indent=2
        )

        messages = [
            SystemMessage(
                content=system_prompt
            ),
            HumanMessage(
                content=(
                    "Voici l'état réel actuel de Nexus.\n\n"
                    f"{context_text}\n\n"
                    "Analyse cet état et indique la prochaine "
                    "priorité logique."
                )
            )
        ]

        try:

            response = await self.llm.ainvoke(
                messages
            )

            decision = response.content.strip()

            print(
                f"Raisonnement Nexus : "
                f"{decision[:300]}"
            )

            self.event(
                "AI_CONSULT",
                "completed",
                action="Analyse du contexte terminée",
                details=decision[:3000],
                result=decision
            )

            self.memory.log_action(
                task_name="Vérification Autonome",
                result=decision[:1000],
                revenue=0.0,
                department="ai",
                progress_step="AI_CONSULT"
            )

        except Exception as e:

            error_message = str(e)

            self.event(
                "AI_CONSULT",
                "error",
                action="Échec de consultation IA",
                details=error_message,
                result="Aucune décision IA produite"
            )

            self.memory.log_action(
                task_name="Erreur IA",
                result=error_message,
                revenue=0.0,
                department="ai",
                progress_step="ERROR"
            )

        # ====================================================
        # 4. FIN DU CYCLE
        # ====================================================

        self.event(
            "OBSERVE",
            "completed",
            action="Cycle Nexus terminé",
            result="Le moteur revient en attente du prochain cycle"
        )

        print(
            "================================================"
        )

    # ========================================================
    # BOUCLE AUTONOME
    # ========================================================

    async def start_autonomous_loop(
        self,
        interval_seconds=1800
    ):

        print(
            "Nexus tourne en arrière-plan et écoute "
            "les ordres..."
        )

        self.event(
            "SYSTEM",
            "started",
            action="Boucle autonome démarrée",
            details=f"Intervalle : {interval_seconds} secondes"
        )

        while True:

            try:

                await self.run_cycle()

            except Exception as e:

                error_message = str(e)

                print(
                    f"Erreur critique dans la boucle : "
                    f"{error_message}"
                )

                self.event(
                    "SYSTEM",
                    "error",
                    action="Erreur critique de boucle",
                    details=error_message
                )

            await asyncio.sleep(
                interval_seconds
            )


# ============================================================
# 5. POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    bot = NexusCore()

    asyncio.run(
        bot.run_cycle()
    )
```
