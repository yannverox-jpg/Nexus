import asyncio
import json
import hmac
import hashlib
import time
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from ghost_meta_kernel import LLMTryptychController
from ghost_institutional_predictive_engine import TopologicalCointegrationGraph, CognitiveReadinessManager
from task_persistence_db import NexusDatabaseManager

router = APIRouter()

MASTER_KEY = "SECURE_CORP_MASTER_KEY_9981"
db_mgr = NexusDatabaseManager()
llm_tryptych = LLMTryptychController()
topo_graph = TopologicalCointegrationGraph()
readiness_mgr = CognitiveReadinessManager()

def verify_hmac_signature(timestamp: str, nonce: str, payload_str: str, signature: str) -> bool:
    message = f"{timestamp}.{nonce}.{payload_str}".encode('utf-8')
    expected_sig = hmac.new(MASTER_KEY.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)

@router.websocket("/ws/v1/nexus-stream")
async def nexus_websocket_stream(websocket: WebSocket):
    """
    Pont WebSocket MCP natif bi-directionnel sécurisé par HMAC-SHA256.
    Canaux de discussion directe Multi-Agents (gemini, gpt, claude) & MCP Tool Calling.
    """
    await websocket.accept()
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg_data = json.loads(raw_text)
            except Exception:
                await websocket.send_json({"status": "ERROR", "detail": "Invalid JSON payload."})
                continue

            # Check HMAC signature if present
            sig = msg_data.get("signature")
            timestamp = str(msg_data.get("timestamp", ""))
            nonce = str(msg_data.get("nonce", ""))
            payload_content = json.dumps(msg_data.get("payload", {}), sort_keys=True)

            if sig and not verify_hmac_signature(timestamp, nonce, payload_content, sig):
                await websocket.send_json({"status": "UNAUTHORIZED", "detail": "HMAC-SHA256 signature mismatch."})
                continue

            target = msg_data.get("target", "").lower()
            payload = msg_data.get("payload", {})
            user_message = payload.get("message", "")

            # MCP Tool Calling handling
            mcp_tool = msg_data.get("mcp_tool")
            if mcp_tool == "query_ghost_memory":
                short_mem = db_mgr.get_recent_market_events(limit=10)
                await websocket.send_json({"status": "TOOL_RESPONSE", "tool": mcp_tool, "data": short_mem})
                continue
            elif mcp_tool == "get_topological_matrix":
                matrix = topo_graph.detect_structural_distortion()
                await websocket.send_json({"status": "TOOL_RESPONSE", "tool": mcp_tool, "data": matrix})
                continue
            elif mcp_tool == "evaluate_readiness_status":
                readiness = readiness_mgr.calculate_readiness_maturity()
                await websocket.send_json({"status": "TOOL_RESPONSE", "tool": mcp_tool, "data": readiness})
                continue

            # Multi-agent chat routing
            if target == "gemini":
                intel = llm_tryptych.gemini_web_recon(user_message)
                db_mgr.save_ai_decision(f"dec_gemini_{int(time.time())}", intel, {}, {}, 100.0)
                await websocket.send_json({
                    "channel": "GEMINI_RADAR",
                    "response": f"Radar Macro: {intel['intel']}",
                    "data": intel
                })
            elif target == "gpt":
                structured = llm_tryptych.gpt_structurer(user_message)
                db_mgr.save_ai_decision(f"dec_gpt_{int(time.time())}", {}, structured, {}, 100.0)
                await websocket.send_json({
                    "channel": "GPT_TOPOLOGY",
                    "response": f"Translation Topologique: {structured['structured_json']}",
                    "data": structured
                })
            elif target == "claude":
                dec = llm_tryptych.claude_self_code_and_decide()
                db_mgr.save_ai_decision(f"dec_claude_{int(time.time())}", {}, {}, dec, 100.0)
                await websocket.send_json({
                    "channel": "CLAUDE_STRATEGIST",
                    "response": f"Synthèse Souveraine: {dec['strategy']}",
                    "data": dec
                })
            else:
                # Echo telemetry stream
                tasks = db_mgr.get_all_tasks()
                await websocket.send_json({
                    "channel": "SYSTEM_STREAM",
                    "tasks_count": len(tasks),
                    "readiness": readiness_mgr.calculate_readiness_maturity()
                })

    except WebSocketDisconnect:
        print("🔌 [WS MCP PROXY] Replit / APK App disconnected.")
