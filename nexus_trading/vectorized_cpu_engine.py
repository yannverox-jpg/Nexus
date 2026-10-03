import numpy as np

class CPUVectorizedLiquidityEngine:
    def __init__(self, num_pairs: int = 29, buffer_size: int = 100, max_spread_pips: float = 0.8):
        self.num_pairs = num_pairs
        self.buffer_size = buffer_size
        self.max_spread_pips = max_spread_pips

        # Buffers contigus en mémoire C (Allocation unique float32 pour registres SIMD CPU)
        self.bids = np.zeros((num_pairs, buffer_size), dtype=np.float32)
        self.asks = np.zeros((num_pairs, buffer_size), dtype=np.float32)
        self.timestamps = np.zeros((num_pairs, buffer_size), dtype=np.float64)
        self.curr_idx = 0

    def push_tick_batch(self, bids_batch: np.ndarray, asks_batch: np.ndarray, times_batch: np.ndarray):
        """Ingestion matricielle simultanée des 29 paires."""
        self.bids[:, self.curr_idx] = bids_batch
        self.asks[:, self.curr_idx] = asks_batch
        self.timestamps[:, self.curr_idx] = times_batch
        self.curr_idx = (self.curr_idx + 1) % self.buffer_size

    def scan_single_best_opportunity(self) -> tuple:
        """Calcul SIMD instantané des 29 paires. Retourne la meilleure opportunité."""
        prev_idx = (self.curr_idx - 1) % self.buffer_size
        old_idx = (self.curr_idx - 15) % self.buffer_size

        latest_bids = self.bids[:, prev_idx]
        old_bids = self.bids[:, old_idx]
        latest_asks = self.asks[:, prev_idx]
        latest_times = self.timestamps[:, prev_idx]
        old_times = self.timestamps[:, old_idx]

        spreads = latest_asks - latest_bids
        time_deltas = np.maximum(latest_times - old_times, 0.001)
        price_deltas = latest_bids - old_bids
        velocity = np.abs(price_deltas) / time_deltas

        valid_spread_mask = spreads <= (self.max_spread_pips * 0.0001)
        explosion_scores = np.where(valid_spread_mask, velocity / (spreads + 1e-6), 0.0)

        best_pair_idx = int(np.argmax(explosion_scores))
        best_score = float(explosion_scores[best_pair_idx])

        if best_score > 25.0:
            direction = 1 if price_deltas[best_pair_idx] > 0 else -1
            return best_pair_idx, direction, best_score, float(spreads[best_pair_idx])

        return None, 0, 0.0, 0.0
