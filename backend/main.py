# backend/main.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import uuid
import os
import json

from modules.run_agent_module import run_agent
from modules.action_extractor_module import extract_actions
from modules.action_annotator_module import annotate_actions

app = FastAPI()

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exploration Mode: run agent → extract → annotate
@app.websocket("/ws/agent")
async def agent_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        url = data["url"]
        task = data["instruction"]

        # session id = uuid + timestamp
        session_id = str(uuid.uuid4())[:8]

        # Step 1: 日志回调
        async def send_log(line: str):
            await websocket.send_text(f"[log] {line}")

        await send_log(f"🧠 Running agent on {url} (Session {session_id})...")

        # Step 2: run agent
        log_path = await run_agent(url, task, log_callback=send_log)
        await send_log(f"✅ Agent finished. Log saved at {log_path}")

        # Step 3: send log content
        with open(log_path, "r") as f:
            log_content = f.read()

        await websocket.send_json({
            "type": "agent_log_text",
            "log_text": log_content,
            "log_path": log_path,
            "session_id": session_id
        })

        # Step 4: extract actions
        await send_log("🔍 Extracting actions from log...")
        extracted = extract_actions(log_content)
        await send_log(f"✅ Extracted {len(extracted)} actions.")

        # Step 5: annotate actions
        await send_log("🧪 Annotating actions with LLM...")
        annotated = annotate_actions(extracted)
        await send_log(f"✅ Annotated {len(annotated)} actions.")

        # Final result
        await websocket.send_json({
            "type": "final_result",
            "annotated_actions": annotated,
            "session_id": session_id
        })

    except WebSocketDisconnect:
        print("🚫 WebSocket disconnected.")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })

# Analysis Mode: upload log → extract → annotate
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

        # Step 1: try to parse as JSON first
        try:
            parsed = json.loads(log_text)

            def is_valid_action(item):
                return (
                    isinstance(item, dict)
                    and "id" in item
                    and "goal" in item
                    and "action_type" in item
                    and "action_detail" in item
                )

            if isinstance(parsed, list) and all(is_valid_action(item) for item in parsed):
                await send_log("📄 Detected uploaded JSON is a valid action list — skipping extraction.")
                extracted = parsed
            else:
                # Fallback: treat as raw log
                await send_log("🔍 Uploaded JSON is not a valid action list — extracting actions...")
                extracted = extract_actions(log_text)
                await send_log(f"✅ Extracted {len(extracted)} actions.")

        except json.JSONDecodeError:
            # Not JSON, treat as raw log
            await send_log("🔍 Detected raw log — extracting actions...")
            extracted = extract_actions(log_text)
            await send_log(f"✅ Extracted {len(extracted)} actions.")

        # Step 2: annotate
        await send_log("🧪 Annotating actions with LLM...")
        annotated = annotate_actions(extracted)
        await send_log(f"✅ Annotated {len(annotated)} actions.")

        # Final result
        await websocket.send_json({
            "type": "final_result",
            "annotated_actions": annotated,
            "session_id": session_id
        })

    except WebSocketDisconnect:
        print("🚫 WebSocket disconnected.")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


# Download endpoint (optional, for saving)
@app.post("/download")
async def download(request: Request):
    try:
        data = await request.json()
        annotated_actions = data.get("annotated_actions", [])
        session_id = data.get("session_id", str(uuid.uuid4())[:8])

        os.makedirs("downloads", exist_ok=True)
        output_path = os.path.join("downloads", f"annotated_{session_id}.json")

        with open(output_path, "w") as f:
            json.dump(annotated_actions, f, indent=2)

        return JSONResponse({
            "status": "ok",
            "path": output_path,
            "count": len(annotated_actions)
        })

    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)
