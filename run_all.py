import subprocess
import time
import sys
import os
import signal

def main():
    print("=== LANCEMENT DE L'ÉCOSYSTÈME INDUSTRIEL NEXUS (RUN_ALL) ===")
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    engine_process = None
    web_process = None

    def shutdown_handler(sig, frame):
        print("\n[!] Signal d'arrêt intercepté. Fermeture propre des processus Nexus...")
        if engine_process and engine_process.poll() is None:
            engine_process.terminate()
        if web_process and web_process.poll() is None:
            web_process.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        while True:
            # 1. Surveillance du moteur (main.py)
            if engine_process is None or engine_process.poll() is not None:
                print("[*] Lancement / Redémarrage du moteur orchestrateur (main.py)...")
                engine_process = subprocess.Popen([sys.executable, "main.py"])

            # 2. Surveillance du tableau de bord web (nexus_dashboard.py)
            if web_process is None or web_process.poll() is not None:
                print("[*] Lancement / Redémarrage du serveur web (nexus_dashboard.py)...")
                web_process = subprocess.Popen([sys.executable, "nexus_dashboard.py"])

            time.sleep(3)

    except Exception as e:
        print(f"[!] Erreur critique dans l'orchestrateur run_all : {e}")
        shutdown_handler(None, None)

if __name__ == "__main__":
    main()
