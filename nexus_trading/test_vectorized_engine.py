import unittest
import numpy as np
from vectorized_cpu_engine import CPUVectorizedLiquidityEngine
from mcp_gemini_controller import GeminiActionResponse, execute_gemini_decision, get_position_state

class TestVectorizedEngine(unittest.TestCase):

    def test_engine_initialization(self):
        engine = CPUVectorizedLiquidityEngine(num_pairs=29, buffer_size=100)
        self.assertEqual(engine.bids.shape, (29, 100))
        self.assertEqual(engine.asks.shape, (29, 100))
        self.assertEqual(engine.timestamps.shape, (29, 100))

    def test_push_and_scan_no_opportunity(self):
        engine = CPUVectorizedLiquidityEngine(num_pairs=29, buffer_size=100)
        bids = np.ones(29, dtype=np.float32) * 1.1000
        asks = np.ones(29, dtype=np.float32) * 1.1005
        times = np.ones(29, dtype=np.float64) * 1000.0

        for _ in range(20):
            engine.push_tick_batch(bids, asks, times)

        pair_idx, direction, score, spread = engine.scan_single_best_opportunity()
        self.assertIsNone(pair_idx)
        self.assertEqual(direction, 0)
        self.assertEqual(score, 0.0)

    def test_push_and_scan_high_velocity_opportunity(self):
        engine = CPUVectorizedLiquidityEngine(num_pairs=29, buffer_size=100)

        # Fill buffer with baseline ticks at t = 100.0
        bids = np.ones(29, dtype=np.float32) * 1.1000
        asks = np.ones(29, dtype=np.float32) * 1.1002  # Spread = 0.0002 (2 pips <= 0.8 pips? wait, 0.8 pips = 0.00008 or 0.0008 depending on scale, code checks <= max_spread_pips * 0.0001 = 0.00008)

        # Let's set tight spread: 0.00005 <= 0.00008
        asks = bids + 0.00005
        times = np.ones(29, dtype=np.float64) * 100.0

        for _ in range(20):
            engine.push_tick_batch(bids, asks, times)

        # Now push tick with price jump on pair 0 at t = 100.01 (0.01s later)
        bids_jump = bids.copy()
        asks_jump = asks.copy()
        bids_jump[0] += 0.0050  # 50 pips jump
        asks_jump[0] += 0.0050
        times_jump = times + 0.01

        engine.push_tick_batch(bids_jump, asks_jump, times_jump)

        pair_idx, direction, score, spread = engine.scan_single_best_opportunity()
        self.assertEqual(pair_idx, 0)
        self.assertEqual(direction, 1)
        self.assertGreater(score, 25.0)

    def test_mcp_gemini_controller_fallback(self):
        state = get_position_state()
        self.assertEqual(state["symbol"], "NONE")
        self.assertEqual(state["ticket"], 0)

        decision = GeminiActionResponse(action="HOLD", reason="Market stable")
        res = execute_gemini_decision(decision)
        self.assertEqual(res["status"], "HOLDING")

if __name__ == "__main__":
    unittest.main()
