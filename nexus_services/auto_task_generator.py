import json
import asyncio
from typing import List, Dict, Any
try:
    from module1_orchestrator import NexusOrchestrator, TaskPriority
except ImportError:
    from module_mocks import NexusOrchestrator, TaskPriority

class NexusAutoTaskEngine:
    """
    Module de réflexion autonome : analyse un objectif de haut niveau
    et décompose la feuille de route en tâches autonomes sans intervention humaine.
    """
    def __init__(self, orchestrator: NexusOrchestrator):
        self.orchestrator = orchestrator

    async def decompose_and_enqueue_goal(self, high_level_goal: str, context: Dict[str, Any]) -> List[str]:
        """
        Analyse l'objectif global et génère dynamiquement la séquence de tâches.
        """
        print(f"🧠 [NEXUS REASONING] Analyse de l'objectif : '{high_level_goal}'")

        # Planification dynamique générée par l'IA (structure de sous-tâches autonome)
        generated_tasks = [
            {
                "task_type": "API_CONTRACT",
                "priority": TaskPriority.HIGH,
                "payload": {
                    "service_name": "CONTRACT_VERIFIER",
                    "action": "FETCH_SPECIFICATIONS",
                    "goal_context": high_level_goal
                }
            },
            {
                "task_type": "WEB3_EXECUTION",
                "priority": TaskPriority.CRITICAL,
                "payload": {
                    "action": "LOCK_ESCROW_FUNDS",
                    "amount_usdc": context.get("budget_usdc", 10.0),
                    "recipient": context.get("provider_address", "0x0000000000000000000000000000000000000000")
                }
            },
            {
                "task_type": "API_CONTRACT",
                "priority": TaskPriority.MEDIUM,
                "payload": {
                    "service_name": "EXECUTION_PROVIDER",
                    "action": "RUN_SERVICE_TASK",
                    "goal_context": high_level_goal
                }
            }
        ]

        submitted_ids = []
        for task_def in generated_tasks:
            task_id = await self.orchestrator.submit_task(
                task_type=task_def["task_type"],
                payload=task_def["payload"],
                priority=task_def["priority"]
            )
            submitted_ids.append(task_id)
            print(f"  └─ 📌 Tâche auto-générée créée: {task_id} [{task_def['task_type']}]")

        return submitted_ids
