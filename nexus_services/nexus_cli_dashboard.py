import time
import os
from typing import List, Dict, Any
from task_persistence_db import NexusDatabaseManager

class NexusCLIDashboard:
    """
    Console de suivi synthétique pour visualiser le fonctionnement de Nexus
    (Tâches en cours, réputation des micro-services, statut des wallets et escrows).
    """
    def __init__(self, db_manager: NexusDatabaseManager):
        self.db = db_manager

    def render(self):
        """Affiche un tableau propre récapitulant l'état du système."""
        tasks = self.db.get_all_tasks()

        print("\n" + "=" * 70)
        print("          🖥️   NEXUS TASK DEPARTMENT - LIVE MONITORING   🖥️          ")
        print("=" * 70)

        # Section Tâches
        print(f"\n📋 DERNIÈRES TÂCHES TRAITÉES ({len(tasks)} enregistrées) :")
        print("-" * 70)
        print(f"{'TASK ID':<12} | {'TYPE':<16} | {'PRIORITÉ':<10} | {'STATUT':<12}")
        print("-" * 70)

        for t in tasks[:5]: # Afficher les 5 plus récentes
            status_color = "✅" if t['status'] == "COMPLETED" else "⏳" if t['status'] == "BUSY" else "❌"
            print(f"{t['task_id'][:10]}... | {t['task_type']:<16} | {t['priority']:<10} | {status_color} {t['status']}")

        print("-" * 70)
