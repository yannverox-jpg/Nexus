import time
import asyncio
import numpy as np
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
from vectorized_cpu_engine import CPUVectorizedLiquidityEngine

PAIRS_29 = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    "CHFJPY", "CADJPY", "AUDJPY", "NZDJPY",
    "AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "NZDCHF", "NZDCAD",
    "XAUUSD"
]

class MT5SingleTradeExecutor:
    def __init__(self, magic_number: int = 777999):
        self.magic = magic_number
        self.is_in_position = False

    def open_micro_scalp(self, pair: str, direction: int, lot_size: float = 0.01) -> bool:
        if mt5 is None:
            print("MetaTrader5 not available.")
            return False
        tick = mt5.symbol_info_tick(pair)
        if not tick:
            return False

        order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == 1 else tick.bid
        dev = 20 if "XAU" in pair else 5

        # AUCUN TP NI SL DANS LA REQUÊTE BROKER (Invisibilité totale)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pair,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "deviation": dev,
            "magic": self.magic,
            "comment": "Nexus-CPU-MicroScalp",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🔥 [ORDER EXECUTED] {pair} | Dir: {direction} | Price: {price}")
            self.is_in_position = True
            return True
        else:
            print(f"❌ [ORDER FAILED] Code: {result.retcode if result else 'UNKNOWN'}")
            return False

async def main():
    if mt5 is None or not mt5.initialize():
        print("Erreur d'initialisation MetaTrader 5.")
        return

    print("✅ MetaTrader 5 Connecté.")
    for pair in PAIRS_29:
        mt5.symbol_select(pair, True)

    engine = CPUVectorizedLiquidityEngine(num_pairs=len(PAIRS_29), max_spread_pips=0.8)
    executor = MT5SingleTradeExecutor()

    print("🚀 Moteur CPU Vectorisé démarré. Surveillance des 29 paires...")

    bids_buffer = np.zeros(len(PAIRS_29), dtype=np.float32)
    asks_buffer = np.zeros(len(PAIRS_29), dtype=np.float32)
    times_buffer = np.zeros(len(PAIRS_29), dtype=np.float64)

    while True:
        if executor.is_in_position:
            positions = mt5.positions_get(magic=executor.magic)
            if positions is None or len(positions) == 0:
                executor.is_in_position = False
                print("🔄 Position clôturée (via Gemini/MCP). Reprise du scan...")
            await asyncio.sleep(0.05)
            continue

        now = time.time()
        for i, pair in enumerate(PAIRS_29):
            tick = mt5.symbol_info_tick(pair)
            if tick:
                bids_buffer[i] = tick.bid
                asks_buffer[i] = tick.ask
                times_buffer[i] = tick.time_msc / 1000.0 if tick.time_msc else now
            else:
                bids_buffer[i] = 0.0
                asks_buffer[i] = 0.0
                times_buffer[i] = now

        engine.push_tick_batch(bids_buffer, asks_buffer, times_buffer)
        pair_idx, direction, score, spread = engine.scan_single_best_opportunity()

        if pair_idx is not None:
            selected_pair = PAIRS_29[pair_idx]
            print(f"⚡ [OPPORTUNITÉ DÉTECTÉE] Paire: {selected_pair} | Score: {score:.2f} | Spread: {spread:.5f}")
            executor.open_micro_scalp(selected_pair, direction, lot_size=0.01)

        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(main())
