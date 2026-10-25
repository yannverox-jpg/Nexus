import unittest

from nexus_services.auto_task_generator import NexusAutoTaskEngine


class RecordingOrchestrator:
    def __init__(self):
        self.tasks = []

    async def submit_task(self, *, task_type, payload, priority):
        task_id = f"task-{len(self.tasks) + 1}"
        self.tasks.append({
            "task_id": task_id,
            "task_type": task_type,
            "payload": payload,
            "priority": priority,
        })
        return task_id


class GoalCorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def test_goal_id_and_constraints_are_attached_to_every_task(self):
        orchestrator = RecordingOrchestrator()
        engine = NexusAutoTaskEngine(orchestrator)
        context = {
            "goal_id": "goal-test-123",
            "budget_usdc": 5.0,
            "target_amount": 1000,
            "target_currency": "EUR",
            "deadline_at": "2026-10-26T12:00:00+01:00",
            "provider_address": "must-not-be-copied",
        }

        task_ids = await engine.decompose_and_enqueue_goal(
            "Earn revenue from legitimate services", context
        )

        self.assertEqual(len(task_ids), 3)
        self.assertEqual(task_ids, ["task-1", "task-2", "task-3"])
        self.assertEqual(
            {task["payload"]["goal_id"] for task in orchestrator.tasks},
            {"goal-test-123"},
        )
        for task in orchestrator.tasks:
            self.assertEqual(
                task["payload"]["goal_constraints"],
                {
                    "budget_usdc": 5.0,
                    "target_amount": 1000,
                    "target_currency": "EUR",
                    "deadline_at": "2026-10-26T12:00:00+01:00",
                },
            )
            self.assertNotIn("provider_address", task["payload"])

    async def test_goal_ids_are_generated_when_caller_does_not_supply_one(self):
        orchestrator = RecordingOrchestrator()
        engine = NexusAutoTaskEngine(orchestrator)

        await engine.decompose_and_enqueue_goal("Inspect configured capabilities", {})

        ids = {task["payload"]["goal_id"] for task in orchestrator.tasks}
        self.assertEqual(len(ids), 1)
        self.assertTrue(next(iter(ids)))


if __name__ == "__main__":
    unittest.main()
