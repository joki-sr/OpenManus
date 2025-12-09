"""A small local fake LLM used for testing.

This module provides predefined ChatCompletionMessage responses
for deterministic testing without calling the real LLM.
"""

from typing import List
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall


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
                "arguments": '{"command": "create", "path": "/home/zhangsiyi/AgenticAI/OpenManus/workspace/hello1.txt", "file_text": "hello1"}'
            },
            "type": "function"
        }
    ]
)

hello2 = ChatCompletionMessage(
    content="文件已成功创建！我在 `/home/zhangsiyi/AgenticAI/OpenManus/workspace/hello1.txt` 中创建了文件，内容为 'hello1'。",
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


add10e5_1 = ChatCompletionMessage(
    content='\n我来为您创建并执行一个Python程序，使用for循环计算1到100000的加和。\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_add10e5_1',
            function={
                "name": "python_execute",
                "arguments": '{"code":"total = 0\\nfor i in range(1, 100001):\\n    total += i\\nprint(f\\"1到100000的和是: {total}\\")"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='\n用户要求写并执行一个Python程序，用for循环计算1到100000的加和（sum += i）。这是一个很直接的任务，我需要：\n\n1. 创建一个Python程序，使用for循环计算1到100000的和\n2. 执行这个程序\n\n我可以使用python_execute工具来执行这个代码。'
)

add10e5_2 = ChatCompletionMessage(
    content='\n程序已成功执行！计算结果如下：\n\n**执行结果：**\n1到100000的和是：**5,000,050,000**\n\n**程序说明：**\n- 使用了for循环遍历从1到100000的所有整数\n- 通过 `total += i` 逐个累加每个数字\n- 最终得到了总和5,000,050,000\n\n**数学验证：**\n这个结果可以通过数学公式验证：1到n的和 = n(n+1)/2\n- 100000 × 100001 ÷ 2 = 5,000,050,000 ✓\n\n**性能考虑：**\n对于这个计算量（10万次循环），现代计算机可以在毫秒级别完成。\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_add10e5_2',
            function={
                "name": "terminate",
                "arguments": '{"status":"success"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='\n用户要求我写并执行一个Python程序，用for循环计算1到100000的加和。我已经成功执行了这个程序，得到了结果5000050000。'
)

add10e8_1 = ChatCompletionMessage(
    content='\n我来帮你写并执行一个Python程序，用for循环计算1到100000000的加和。\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_add10e8_1',
            function={
                "name": "python_execute",
                "arguments": '{"code": "# 计算1到100000000的加和，使用for循环\\nprint(\\"开始计算1到100000000的加和...\\")\\n\\nsum_result = 0\\nfor i in range(1, 100000001):\\n    sum_result += i\\n\\nprint(f\\"计算完成！\\")\\nprint(f\\"1到100000000的加和为: {sum_result}\\")\\n\\n# 验证结果是否正确（使用数学公式验证）\\nexpected_sum = 100000000 * 100000001 // 2\\nprint(f\\"使用数学公式验证的预期结果: {expected_sum}\\")\\nprint(f\\"结果是否正确: {sum_result == expected_sum}\\")"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='\n用户要求我写并执行一个Python程序，用for循环计算1到100000000（10^8）的加和。用户明确说了不使用数学公式，而是用for循环来做CPU密集型测试。\n\n我需要：\n1. 写一个Python程序，用for循环计算1到100000000的加和\n2. 执行这个程序\n3. 验证结果是否正确\n4. 然后结束\n\n让我先用python_execute工具来写和执行这个程序。'
)

add10e8_2 = ChatCompletionMessage(
    content='\n程序已成功执行并验证完成！\n\n**执行结果：**\n- 使用for循环计算1到100000000的加和\n- 计算结果：5,000,000,050,000,000\n- 通过数学公式验证结果正确\n- 程序执行成功，完成了CPU密集型测试任务\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_add10e8_2',
            function={
                "name": "terminate",
                "arguments": '{"status": "success"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='\n用户要求我写并执行一个Python程序，用for循环计算1到100000000（10e8）的加和，并且明确说了不使用数学公式，只是做CPU密集型测试。我已经成功执行了代码，结果显示：\n\n1. 计算完成\n2. 1到100000000的加和为: 5000000050000000\n3. 使用数学公式验证的预期结果: 5000000050000000\n4. 结果是否正确: True\n\n用户要求我写完代码、执行、结果验证正确之后就结束。现在所有条件都满足了：\n- 代码已写好并执行\n- 结果已验证正确\n- 用户要求结束\n\n我应该使用terminate工具来结束这个交互。'
)

addMemoryFast_1 = ChatCompletionMessage(
    content='\n我来为您创建并执行一个快速内存密集型Python程序，循环生成小批量列表并累加总和，保证执行时间短且内存安全。\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_addMemoryFast_1',
            function={
                "name": "python_execute",
                "arguments": '{"code":"import sys\\ntotal = 0\\nbatch_size = 1_000_000  # 每批 100 万个整数\\nbatches = 3  # 循环3次，总计处理 300 万整数\\nfor i in range(batches):\\n    numbers = list(range(batch_size))\\n    total += sum(numbers)\\n    print(f\\"第{i+1}批完成，占用内存约: {sys.getsizeof(numbers)/1024/1024:.2f} MB\\")\\n    del numbers\\nprint(f\\"最终总和: {total}\\")"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='\n用户要求创建快速内存密集型程序，生成小批量列表循环累加，保持安全且执行时间短。'
)

addMemoryFast_2 = ChatCompletionMessage(
    content='\n程序已成功执行！计算结果如下：\n\n**执行结果：**\n最终总和是：**4500000000000**\n\n**程序说明：**\n- 循环生成3批 100 万个整数的列表\n- 每批使用 sum() 计算并累加到总和\n- 内存峰值约 28MB，执行速度快，和 add10e5 差不多\n',
    role='assistant',
    tool_calls=[
        ChatCompletionMessageToolCall(
            id='call_addMemoryFast_2',
            function={
                "name": "terminate",
                "arguments": '{"status":"success"}'
            },
            type='function',
            index=0
        )
    ],
    refusal=None,
    annotations=None,
    audio=None,
    function_call=None,
    reasoning_content='程序安全执行，单批生成列表并释放，执行时间短且内存使用低。'
)

# FakeLLMInstance = FakeLLM([hello0, hello1, hello2])
# FakeLLMInstance = FakeLLM([add10e5_1, add10e5_2])
# FakeLLMInstance = FakeLLM([add10e8_1, add10e8_2])
FakeLLMInstance = FakeLLM([addMemoryFast_1, addMemoryFast_2])
