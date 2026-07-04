import asyncio
import time
from typing import List, Optional
from tasks.llm_queue import process_llm_request, process_tool_call
from src.loggers import Logger

logger = Logger(__name__).get_logger()

class TaskManager:
    def __init__(self):
        self.pending_tasks = {}

    async def submit_llm_task(self, prompt: str, provider: str = "groq", timeout: int = 30):
        """Submit LLM task to queue and wait for result with timeout"""
        try:
            # Submit task to Celery
            task = process_llm_request.delay(prompt, provider)
            self.pending_tasks[task.id] = task

            # Wait for result with timeout
            start_time = time.time()
            while not task.ready():
                if time.time() - start_time > timeout:
                    task.revoke()  # Cancel the task
                    del self.pending_tasks[task.id]
                    raise TimeoutError(f"LLM task timeout after {timeout} seconds")

                await asyncio.sleep(0.1)  # Yield control

            del self.pending_tasks[task.id]

            if task.successful():
                return task.result
            else:
                logger.error(f"LLM task failed: {task.result}")
                raise Exception(f"LLM task failed: {task.result}")

        except Exception as e:
            logger.error(f"Error submitting LLM task: {e}")
            raise

    async def submit_tool_task(self, tool_name: str, tool_args: dict, timeout: int = 30):
        """Submit tool call to background worker"""
        try:
            task = process_tool_call.delay(tool_name, tool_args)

            # Wait for result with timeout
            start_time = time.time()
            while not task.ready():
                if time.time() - start_time > timeout:
                    task.revoke()
                    raise TimeoutError(f"Tool task timeout after {timeout} seconds")

                await asyncio.sleep(0.1)

            if task.successful():
                return task.result
            else:
                logger.error(f"Tool task failed: {task.result}")
                raise Exception(f"Tool task failed: {task.result}")

        except Exception as e:
            logger.error(f"Error submitting tool task: {e}")
            raise

    async def batch_llm_calls(self, prompts: List[str], provider: str = "groq"):
        """Batch process multiple LLM calls concurrently"""
        tasks = [self.submit_llm_task(prompt, provider) for prompt in prompts]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def process_concurrent_tools(self, tool_calls: List[dict]):
        """Process multiple tool calls concurrently"""
        tasks = []
        for tool_call in tool_calls:
            task = self.submit_tool_task(
                tool_call["name"],
                tool_call["args"]
            )
            tasks.append(task)

        return await asyncio.gather(*tasks, return_exceptions=True)

# Global task manager instance
task_manager = TaskManager()
