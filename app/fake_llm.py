"""A small local fake LLM used for testing.

This module provides predefined ChatCompletionMessage responses
for deterministic testing without calling the real LLM.
"""

from typing import List
from openai.types.chat import ChatCompletionMessage


class FakeLLM:
    """A mock LLM that cycles through predefined ChatCompletionMessage responses."""

    def __init__(self, responses: List[ChatCompletionMessage]):
        self.responses = responses
        self.index = 0

    async def ask_tool(self, messages, system_msgs=None, tools=None, tool_choice=None):
        # Return the next response in a round-robin fashion.
        resp = self.responses[self.index]
        self.index = (self.index + 1) % len(self.responses)
        return resp


# Build three predefined ChatCompletionMessage responses for testing.
hello0 = ChatCompletionMessage(
    content="I'll help you create a file named 'hello1.txt' with the content 'hello1' and save it.",
    role='assistant',
    tool_calls=[
        {
            "id": "call_1",
            "function": {
                "name": "str_replace_editor",
                "arguments": '{"command": "create", "path": "hello1.txt", "file_text": "hello1"}'
            },
            "type": "function"
        }
    ]
)

hello1 = ChatCompletionMessage(
    content="I need to use the absolute path. Let me create the file with the correct path.",
    role='assistant',
    tool_calls=[
        {
            "id": "call_2",
            "function": {
                "name": "str_replace_editor",
                "arguments": '{"command": "create", "path": "/mnt/e/Development/AgentAI/OpenManus/workspace/hello1.txt", "file_text": "hello1"}'
            },
            "type": "function"
        }
    ]
)

hello2 = ChatCompletionMessage(
    content="文件已成功创建！我在 `/mnt/e/Development/AgentAI/OpenManus/workspace/hello1.txt` 中创建了文件，内容为 'hello1'。",
    role='assistant',
    tool_calls=[
        {
            "id": "call_3",
            "function": {
                "name": "terminate",
                "arguments": '{"status": "success"}'
            },
            "type": "function"
        }
    ]
)


FakeLLMInstance = FakeLLM([hello0, hello1, hello2])

