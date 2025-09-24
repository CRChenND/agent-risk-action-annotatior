# backend/main.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import asyncio
import uuid
import os
import json
from pathlib import Path
import time

from modules.run_agent_module import run_agent
from modules.action_extractor_module import parse_jsonl_to_combined
from modules.action_annotator_module import annotate_pairs

app = FastAPI()

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 小工具 ----------

def _read_text(p: str | Path) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

def _write_text(p: str | Path, s: str) -> str:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")
    return str(p)

def _is_combined_records(obj) -> bool:
    """
    简单校验是否为 combined 结构（你现在的解析输出）：
    - list of dict，且每条包含 kind/ts/url/action
    """
    if not isinstance(obj, list) or not obj:
        return False
    head = obj[0]
    return (
        isinstance(head, dict)
        and "kind" in head
        and "ts" in head
        and "url" in head
        and "action" in head
    )

# ---------- Exploration Mode: run agent → extract(combined) → annotate(pairs) ----------

@app.websocket("/ws/agent")
async def agent_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        url = data["url"]
        task = data["instruction"]
        max_steps = data.get("max_steps", 10)

        session_id = str(uuid.uuid4())[:8]

        async def send_log(line: str):
            await websocket.send_text(f"[log] {line}")

        await send_log(f"🧠 Running agent on {url} (Session {session_id})...")

        # Step 1: run agent -> 返回 JSONL 路径
        # 你的 run_agent 接口如果是 (task, url, max_steps) 记得按你的实现调整
        log_path = await run_agent(
            task=task,
            url=url,
            max_steps=max_steps,
            log_callback=send_log,  # 可选：若你的 run_agent 支持
        )
        await send_log(f"✅ Agent finished. Log saved at {log_path}")

        # 把日志全文发给前端展示
        log_text = await asyncio.to_thread(_read_text, log_path)
        await websocket.send_json({
            "type": "agent_log_text",
            "log_text": log_text,
            "log_path": log_path,
            "session_id": session_id
        })

        # Step 2: extract → combined（仅输出 combined）
        await send_log("🔍 Extracting combined actions from JSONL log...")
        combined_path = await asyncio.to_thread(parse_jsonl_to_combined, log_path, None)
        combined = json.loads(await asyncio.to_thread(_read_text, combined_path))
        await send_log(f"✅ Combined parsed: {len(combined)} records. ({combined_path})")

        # Step 3: annotate → 按 planned↔executed pair
        await send_log("🧪 Annotating planned↔executed pairs with LLM...")
        annotated_combined = await asyncio.to_thread(annotate_pairs, combined)
        await send_log(f"✅ Annotated {len(annotated_combined)} records.")

        # 最终结果
        payload = {
            "type": "final_result",
            "annotated_combined": annotated_combined,
            "combined_path": combined_path,  # 可以是 Path
            "session_id": session_id,
        }
        await websocket.send_json(jsonable_encoder(payload))

    except WebSocketDisconnect:
        print("🚫 WebSocket disconnected.")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })

# ---------- Analysis Mode: upload JSONL(text) → extract(combined) → annotate(pairs) ----------

@app.websocket("/ws/analyze")
async def analyze_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        log_text = data["log_text"]
        session_id = str(uuid.uuid4())[:8]

        async def send_log(line: str):
            await websocket.send_text(f"[log] {line}")

        await send_log(f"🔍 Analyzing uploaded log (Session {session_id})...")

        # 1) 用户可能直接上传的是 combined JSON（而不是 JSONL）
        try:
            parsed_json = json.loads(log_text)
            if _is_combined_records(parsed_json):
                await send_log("📄 Detected uploaded JSON is combined records — skipping extraction.")
                combined = parsed_json
            else:
                # 不是 combined，就按 JSONL 处理
                raise ValueError("Not combined JSON. Fallthrough to JSONL.")
        except Exception:
            # 2) 当作 JSONL：先落盘，再解析
            await send_log("📄 Treating upload as JSONL. Parsing to combined...")
            tmp_dir = Path("uploads")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_jsonl = tmp_dir / f"uploaded_{session_id}.jsonl"
            await asyncio.to_thread(_write_text, tmp_jsonl, log_text)

            combined_path = await asyncio.to_thread(parse_jsonl_to_combined, str(tmp_jsonl), None)
            combined = json.loads(await asyncio.to_thread(_read_text, combined_path))
            await send_log(f"✅ Combined parsed: {len(combined)} records. ({combined_path})")

        # 3) annotate pairs
        await send_log("🧪 Annotating planned↔executed pairs with LLM...")
        annotated_combined = await asyncio.to_thread(annotate_pairs, combined)
        await send_log(f"✅ Annotated {len(annotated_combined)} records.")

        # 输出
        await websocket.send_json({
            "type": "final_result",
            "annotated_combined": annotated_combined,
            "session_id": session_id
        })

    except WebSocketDisconnect:
        print("🚫 WebSocket disconnected.")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


# ---------- Download endpoint ----------

@app.post("/download")
async def download(request: Request):
    try:
        data = await request.json()
        annotated_combined = data.get("annotated_combined", [])
        session_id = data.get("session_id", str(uuid.uuid4())[:8])

        os.makedirs("downloads", exist_ok=True)
        output_path = os.path.join("downloads", f"annotated_{session_id}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(annotated_combined, f, ensure_ascii=False, indent=2)

        return JSONResponse({
            "status": "ok",
            "path": output_path,
            "count": len(annotated_combined)
        })

    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)
