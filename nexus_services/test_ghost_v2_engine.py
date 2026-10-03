import unittest
import asyncio
from ghost_institutional_predictive_engine import (
    AssetVectorState,
    SpreadVectorState,
    TopologicalCointegrationGraph,
    MCPTryptychOrchestrator
)

class TestGhostV2Engine(unittest.IsolatedAsyncioTestCase):

    def test_asset_and_spread_vectors(self):
        asset = AssetVectorState("USD")
        asset.update_vector(0.0015, 2.5, 0.4, 0.2, 120.0, 10.0)
        self.assertEqual(asset.to_dict()["v_speed"], 2.5)

        spread = SpreadVectorState("EURUSD")
        spread.update_spread(0.0003, 0.00005, 0.00001, 0.8, 0.00010)
        rep = spread.generate_liquidity_report()
        self.assertEqual(rep["orderbook_status"], "REPELLENT_STRESSED")

    async def test_topological_graph_and_mcp_orchestration(self):
        graph = TopologicalCointegrationGraph()
        graph.asset_states["USD"].v_speed = 3.0
        graph.spread_states["EURUSD"].z_spread_stress = 0.8

        distortions = graph.detect_structural_distortion()
        self.assertTrue(len(distortions) > 0)
        self.assertEqual(distortions[0]["leading_asset"], "USD")

        mcp = MCPTryptychOrchestrator(graph)
        synthesis = await mcp.run_mcp_synthesis_cycle("FOMC Rate Announcement")
        self.assertEqual(synthesis["active_mode"], "SOVEREIGN_PREDICTIVE_SENTINEL_V2")
        self.assertEqual(synthesis["claude"]["zero_treasury_policy"], "STRICT_ANALYTICAL_SENTINEL_MODE")

if __name__ == "__main__":
    unittest.main()
