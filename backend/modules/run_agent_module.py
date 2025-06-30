# run_agent_module.py
import asyncio
import os
import datetime
import logging
from dotenv import load_dotenv
from pydantic import SecretStr
from browser_use import Agent
from langchain_openai import ChatOpenAI

# ✅ 加载环境变量
load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY', '')
if not api_key:
	raise ValueError('OPENROUTER_API_KEY is not set')

# ✅ 主函数
async def run_agent(url: str, task: str, log_callback=None, max_steps: int = 10) -> str:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"session_{timestamp}.log")

    # 设置文件日志 handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s'))
    agent_logger = logging.getLogger("browser_use")
    agent_logger.setLevel(logging.INFO)
    agent_logger.addHandler(file_handler)

    try:
        agent = Agent(
            task=f'{task} in {url}.',
            llm=ChatOpenAI(
                base_url='https://openrouter.ai/api/v1',
                model='openai/gpt-4o-mini', 
                api_key=SecretStr(api_key),
            ),
            use_vision=False,
            message_context=(
                'You are a privacy-conscious AI Agent. Your primary objective is to perform the task '
                'while maintaining discretion and security.'
            )
        )

        await agent.run(max_steps=max_steps)

    finally:
        agent_logger.removeHandler(file_handler)
        file_handler.close()

    return log_path
