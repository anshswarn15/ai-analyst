"""Scripted LLM used to test the agent loop deterministically (no network, no API key)."""
from app.llm.client import LLMResponse, ToolCall


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.script.pop(0)


def tool(name, **args):
    import json
    return ToolCall(id=f"call_{name}", name=name, arguments=args, raw_arguments=json.dumps(args))


def reply(text):
    return LLMResponse(content=text, usage={"prompt_tokens": 10, "completion_tokens": 5})


def calls(*tcs):
    return LLMResponse(content=None, tool_calls=list(tcs), usage={"prompt_tokens": 10, "completion_tokens": 5})
