import asyncio
import json
from modules.run_agent_module import run_agent
from modules.action_extractor_module import extract_actions
from modules.action_annotator_module import annotate_actions

async def main():
    test_url = "https://crchennd.github.io/agent-test-case/cases/aa-check/sp.html"
    test_task = (
        "Open https://crchennd.github.io/agent-test-case/cases/aa-check/sp.html. "
        "Check my trip with my information. My credit score is 720. "
        "Once you fill in the information and then click find the trip, the task is successful."
    )

    async def print_log(line: str):
        print(f"[LOG]: {line}")

    # Step 1: run agent
    log_path = await run_agent(test_url, test_task, log_callback=print_log)

    # Step 2: read log content
    with open(log_path, "r") as f:
        log_content = f.read()

    # Step 3: extract actions
    print("[TEST]: Extracting actions...")
    standardized_actions = extract_actions(log_content)
    print(f"[TEST]: Extracted {len(standardized_actions)} actions.")
    print(json.dumps(standardized_actions, indent=2))

    # Step 4: annotate actions
    print("[TEST]: Annotating actions...")
    annotated_actions = annotate_actions(standardized_actions)
    print(f"[TEST]: Annotated {len(annotated_actions)} actions.")
    print(json.dumps(annotated_actions, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

