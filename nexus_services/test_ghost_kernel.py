import unittest
import asyncio
from ghost_meta_kernel import (
    CognitivePipeline,
    LLMTryptychController,
    HumanInTheLoopGateway,
    DynamicCapabilityRegistry
)

class TestGhostMetaKernel(unittest.IsolatedAsyncioTestCase):

    async def test_cognitive_pipeline_control_pass(self):
        pipeline = CognitivePipeline(min_risk_reward_ratio=2.0)
        input_data = {"signal_id": "SIG-100", "symbol": "XAUUSD", "rr_ratio": 2.5, "proposed_action": "BUY"}
        res = await pipeline.run_pipeline(input_data)
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["symbol"], "XAUUSD")

    async def test_cognitive_pipeline_control_blocked(self):
        pipeline = CognitivePipeline(min_risk_reward_ratio=2.0)
        input_data = {"signal_id": "SIG-101", "symbol": "EURUSD", "rr_ratio": 1.2, "proposed_action": "SELL"}
        res = await pipeline.run_pipeline(input_data)
        self.assertEqual(res["status"], "BLOCKED_BY_CONTROL")

    def test_llm_tryptych_and_self_healing(self):
        controller = LLMTryptychController()
        patch_res = controller.claude_self_code_and_decide(err_trace="Traceback Error in module")
        self.assertEqual(patch_res["status"], "PATCH_GENERATED")
        self.assertEqual(patch_res["target_file"], "ghost_meta_kernel.py")

    def test_hitl_gateway(self):
        hitl = HumanInTheLoopGateway(uncertainty_threshold=0.40)
        hitl_id = hitl.check_hitl_required(0.55, {"action": "LARGE_WITHDRAWAL", "amount": 1000})
        self.assertIsNotNone(hitl_id)
        self.assertTrue(hitl.approve_action(hitl_id))

    def test_dynamic_capability_registry(self):
        registry = DynamicCapabilityRegistry()
        manifest = registry.get_capabilities_manifest()
        self.assertEqual(manifest["kernel_version"], "GHOST-v1.0-SOVEREIGN")
        self.assertIn("trading_engine", manifest["capabilities"])

if __name__ == "__main__":
    unittest.main()
