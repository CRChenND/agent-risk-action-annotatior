import asyncio, time, json
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from browser_use import Agent, ChatOpenAI

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def _safe_last(xs):
    return xs[-1] if xs else None

def _ser(o: Any) -> Any:
    try:
        json.dumps(o)
        return o
    except Exception:
        return str(o)

async def run_agent(
    task: str,
    url: Optional[str] = None,
    max_steps: int = 10,
    model: str = "gpt-4o-mini",
    step_timeout: int = 60,
) -> List[Dict[str, Any]]:
    """
    Run a Browser-Use agent with optional starting URL and return JSON-serializable logs.
    Save logs both as streaming JSONL (one per step) and full JSON (at the end).
    """
    logs: List[Dict[str, Any]] = []
    ts = int(time.time())
    log_file_jsonl = LOG_DIR / f"agent_run_{ts}.jsonl"
    log_file_json = LOG_DIR / f"agent_run_{ts}.json"

    composed_task = f"Open {url} then: {task}" if url else task
    agent = Agent(
        task=composed_task, 
        llm=ChatOpenAI(
            model=model,
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        ), 
        step_timeout=step_timeout
    )

    async def on_step_start(a: "Agent"):
        try:
            current_url = await a.browser_session.get_current_page_url()
        except Exception:
            current_url = None
        try:
            thoughts = a.history.model_thoughts()
        except Exception:
            try:
                thoughts = a.history.model_outputs()
            except Exception:
                thoughts = []
        last_thought = _safe_last(thoughts)
        planned_action = getattr(getattr(a, "state", None), "planned_action", None)
        if planned_action is None:
            try:
                planned_action = _safe_last(a.history.model_actions())
            except Exception:
                planned_action = None
        target = None
        if isinstance(planned_action, dict):
            args = planned_action.get("args") or {}
            target = args.get("selector") or args.get("xpath") or args.get("index") or \
                     args.get("query") or args.get("text") or args.get("url")
        record = {
            "ts": time.time(),
            "phase": "on_step_start",
            "url": current_url,
            "last_thought": _ser(last_thought),
            "planned_action": _ser(planned_action),
            "planned_target": _ser(target),
        }
        logs.append(record)
        with log_file_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def on_step_end(a: "Agent"):
        try:
            current_url = await a.browser_session.get_current_page_url()
        except Exception:
            current_url = None
        try:
            actions = a.history.model_actions()
        except Exception:
            actions = []
        last_action = _safe_last(actions)
        try:
            extracted = a.history.extracted_content()
        except Exception:
            extracted = []
        last_extracted = _safe_last(extracted)
        last_result = getattr(getattr(a, "state", None), "last_action_result", None)
        target = None
        if isinstance(last_action, dict):
            args = last_action.get("args") or {}
            target = args.get("selector") or args.get("xpath") or args.get("index") or \
                     args.get("query") or args.get("text") or args.get("url")
        record = {
            "ts": time.time(),
            "phase": "on_step_end",
            "url": current_url,
            "action": _ser(last_action),
            "target": _ser(target),
            "extracted": _ser(last_extracted),
            "result": _ser(last_result),
        }
        logs.append(record)
        with log_file_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # run agent
    await agent.run(
        on_step_start=on_step_start,
        on_step_end=on_step_end,
        max_steps=max_steps,
    )

    return logs


# ---- 使用示例 ----
if __name__ == "__main__":
    logs = asyncio.run(
        run_agent(
            task=(
                "Check my trip with my information. " 
                "My name is John Doe. "
                "My confirmation number is 123456. " 
                "My credit score is 720. "
            ),
            url="https://crchennd.github.io/agent-test-case/cases/aa-check/im.html",
            max_steps=10,
        )
    )
