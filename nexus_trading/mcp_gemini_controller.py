import time
import numpy as np
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Nexus-MCP-Gemini-Bridge")

class GeminiActionResponse(BaseModel):
    action: str  # "HOLD" ou "CLOSE_NOW"
    reason: str

def get_current_tick_velocity(symbol: str) -> float:
    if mt5 is None:
        return 0.0
    ticks = mt5.copy_ticks_from(symbol, time.time() - 5, 10, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) < 2:
        return 0.0
    times = ticks['time_msc'] / 1000.0
    prices = ticks['bid']
    time_delta = max(times[-1] - times[0], 0.001)
    price_delta = abs(prices[-1] - prices[0])
    return float(price_delta / time_delta)

@app.get("/mcp/position_state")
def get_position_state():
    if mt5 is None:
        return {"symbol": "NONE", "ticket": 0, "profit_pips": 0.0, "duration_seconds": 0.0, "tick_velocity": 0.0}
    positions = mt5.positions_get(group="*")
    if not positions:
        return {"symbol": "NONE", "ticket": 0, "profit_pips": 0.0, "duration_seconds": 0.0, "tick_velocity": 0.0}

    pos = positions[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    curr_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
    multiplier = 100.0 if "JPY" in pos.symbol or "XAU" in pos.symbol else 10000.0
    direction_factor = 1 if pos.type == mt5.POSITION_TYPE_BUY else -1
    profit_pips = (curr_price - pos.price_open) * direction_factor * multiplier

    return {
        "symbol": pos.symbol,
        "ticket": pos.ticket,
        "entry_price": pos.price_open,
        "current_price": curr_price,
        "profit_pips": profit_pips,
        "direction": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
        "duration_seconds": time.time() - pos.time,
        "tick_velocity": get_current_tick_velocity(pos.symbol)
    }

@app.post("/mcp/execute_gemini_decision")
def execute_gemini_decision(decision: GeminiActionResponse):
    if decision.action == "CLOSE_NOW":
        if mt5 is None:
            return {"status": "FAILED", "reason": "MetaTrader5 not available"}
        positions = mt5.positions_get(group="*")
        if positions:
            pos = positions[0]
            tick = mt5.symbol_info_tick(pos.symbol)
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 10,
                "magic": pos.magic,
                "comment": "Gemini-MCP-InvisibleCut",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            return {"status": "CLOSED", "retcode": res.retcode, "reason": decision.reason}
    return {"status": "HOLDING", "reason": decision.reason}

if __name__ == "__main__":
    import uvicorn
    if mt5 and mt5.initialize():
        uvicorn.run(app, host="127.0.0.1", port=8000)
