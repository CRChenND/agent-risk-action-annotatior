# action_extractor_module.py

'''
This module extracts and standardizes action trajectories from unstructured logs using OpenRouter's API.
It includes functions to sanitize raw output, validate and standardize actions, and process logs in folders
for batch processing.
'''

import os
import json
import time
from dotenv import load_dotenv
from typing import List, Dict, Any
from pydantic import BaseModel, ValidationError
from openai import OpenAI

# ✅ Load API key
load_dotenv()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

# ✅ Pydantic schema
class ActionItem(BaseModel):
    id: int
    goal: str
    action: Dict[str, Any]

# ✅ 标准化 schema
class StandardizedAction(BaseModel):
    id: int
    goal: str
    action_type: str
    action_detail: Dict[str, Any]

# ✅ 清洗 raw LLM output
def sanitize_raw_output(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw.removeprefix("```json").strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```").strip()
    if raw.endswith("```"):
        raw = raw.removesuffix("```").strip()
    return raw

# ✅ 统一 action schema
def standardize_action(raw_action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a raw extracted action into a standardized action schema.
    """
    action_dict = raw_action.get("action", {})
    goal = raw_action.get("goal", "")
    action_id = raw_action.get("id", -1)

    # 自动推断 action_type
    goal_lower = goal.lower()
    action_str = json.dumps(action_dict).lower()

    if "click" in goal_lower or "click" in action_str:
        action_type = "click"
    elif "input" in goal_lower or "type" in goal_lower:
        action_type = "input_text"
    elif "select" in goal_lower:
        action_type = "select"
    elif "navigate" in goal_lower or "go to" in goal_lower or "visit" in goal_lower:
        action_type = "navigate"
    else:
        action_type = "other"

    return {
        "id": action_id,
        "goal": goal,
        "action_type": action_type,
        "action_detail": action_dict
    }

# ✅ Exposed main function for log extraction
def extract_actions(log_text: str, max_retries=3) -> List[Dict[str, Any]]:
    prompt = f"""
You are an assistant extracting an agent's action trajectory from unstructured logs.

Log:
{log_text}

Please extract the action trajectory as a JSON list. Each item should have:
- "id": unique integer starting from 1
- "goal": a short description of the goal of this action
- "action": the actual action in dictionary format

Only return valid raw JSON (do not wrap in backticks or markdown).
"""

    for attempt in range(1, max_retries + 1):
        try:
            print(f"🌀 Attempt {attempt}...")
            response = client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract JSON action steps from messy agent logs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            raw_output = response.choices[0].message.content
            clean_output = sanitize_raw_output(raw_output)
            raw_actions = json.loads(clean_output)

            # ✅ Validate raw actions
            validated = [ActionItem(**item).dict() for item in raw_actions]

            # ✅ Standardize actions
            standardized = [standardize_action(item) for item in validated]

            return standardized

        except (json.JSONDecodeError, ValidationError) as e:
            print(f"⚠️  Parse/Validation failed on attempt {attempt}: {e}")
            time.sleep(1)

    raise ValueError("❌ All retries failed. Cannot extract valid JSON.")

# ✅ Optional utility: batch process files in folders
def process_logs_in_folder(input_folder: str, output_folder: str):
    os.makedirs(output_folder, exist_ok=True)
    for filename in os.listdir(input_folder):
        if filename.endswith(".txt") or filename.endswith(".log"):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".json")

            print(f"\n🔍 Processing {filename}...")
            with open(input_path, "r") as f:
                log_text = f.read()

            try:
                standardized_actions = extract_actions(log_text)
                with open(output_path, "w") as out_f:
                    json.dump(standardized_actions, out_f, indent=2)
                print(f"✅ Saved to {output_path}")

            except Exception as e:
                print(f"❌ Failed completely for {filename}: {e}")
                with open(output_path.replace(".json", "_error.txt"), "w") as err_f:
                    err_f.write(str(e))
