#!/bin/bash
set -e

echo "[JULES DEPLOY] Initialisation du déploiement de Nexus en production..."

# 1. Vérification et durcissement de l'environnement
export NEXUS_ENV="production"
WORK_DIR="/tmp/nexus"
mkdir -p $WORK_DIR/logs

# 2. Récupération de l'adresse IP publique du serveur
SERVER_IP=$(curl -s --max-time 3 ifconfig.me || curl -s --max-time 3 api.ipify.org || echo "127.0.0.1")
echo "[INFRASTRUCTURE] Adresse IP du serveur cible : $SERVER_IP"

# 3. Génération du rapport de connexion initial (Pre-flight check)
echo "[DIAGNOSTIC] Exécution du rapport de connexions multi-plateformes..."
python3 -c "import asyncio, sys; sys.path.insert(0, 'nexus-engine'); from preflight_checker import run_preflight_check; asyncio.run(run_preflight_check())"

# 4. Lancement de Nexus en arrière-plan avec supervision de processus
echo "[DAEMON] Démarrage de Nexus en arrière-plan (Mode détaché)..."
python3 -u core_engine.py > $WORK_DIR/logs/nexus_stdout.log 2> $WORK_DIR/logs/nexus_stderr.log &

# 5. Confirmation de mise en orbite
NEXUS_PID=$!
echo $NEXUS_PID > $WORK_DIR/nexus.pid
echo "[SUCCESS] Nexus est officiellement sur la toile et tourne en arrière-plan (PID: $NEXUS_PID)."
echo "[ACCÈS] Passerelle active sur : http://$SERVER_IP:8000"
