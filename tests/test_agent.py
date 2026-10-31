"""Offline tests: no Ollama server required.

Run: python3 -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path

from agent import Agent, ToolRegistry, build_default_registry


class FakeLLM:
    """Returns scripted responses so the loop can be tested without a model."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(list(messages))
        return {"message": self.responses.pop(0), "stats": {}}


def tool_call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def answer(text):
    return {"role": "assistant", "content": text}


class ToolSchemaTests(unittest.TestCase):
    def test_schema_from_signature_and_docstring(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str, times: int = 1) -> str:
            """Say hello.

            Args:
                name: Who to greet.
                times: How many times.
            """
            return " ".join([f"hi {name}"] * times)

        fn = registry.schemas()[0]["function"]
        self.assertEqual(fn["name"], "greet")
        self.assertEqual(fn["description"], "Say hello.")
        self.assertEqual(fn["parameters"]["properties"]["times"]["type"], "integer")
        self.assertEqual(fn["parameters"]["properties"]["name"]["description"], "Who to greet.")
        self.assertEqual(fn["parameters"]["required"], ["name"])
        self.assertEqual(registry.call("greet", {"name": "Seho", "times": 2}), "hi Seho hi Seho")

    def test_bad_calls_return_errors_instead_of_raising(self):
        registry = ToolRegistry()

        @registry.register
        def echo(text: str) -> str:
            """Echo text."""
            return text

        self.assertIn("unknown tool", registry.call("nope", {}))
        self.assertIn("missing required", registry.call("echo", {}))
        self.assertIn("unexpected arguments", registry.call("echo", {"text": "a", "x": 1}))


class BuiltinToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "note.txt").write_text("hello", encoding="utf-8")
        self.registry = build_default_registry(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_calculator(self):
        self.assertEqual(self.registry.call("calculator", {"expression": "(12.5 * 4) / 2"}), "25")
        self.assertEqual(self.registry.call("calculator", {"expression": "1847*293/3"}), "180390.3333")
        self.assertIn("Error", self.registry.call("calculator", {"expression": "__import__('os')"}))

    def test_file_tools_stay_inside_workspace(self):
        self.assertEqual(self.registry.call("read_file", {"path": "note.txt"}), "hello")
        self.assertIn("note.txt", self.registry.call("list_files", {}))
        self.assertIn("PermissionError", self.registry.call("read_file", {"path": "../../etc/passwd"}))


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry(Path(tempfile.gettempdir()))

    def test_tool_result_is_fed_back_to_model(self):
        llm = FakeLLM([tool_call("calculator", expression="6*7"), answer("It is 42.")])
        agent = Agent(llm, self.registry)
        self.assertEqual(agent.run("what is 6*7?"), "It is 42.")
        last_seen = llm.calls[1][-1]
        self.assertEqual(last_seen["role"], "tool")
        self.assertEqual(last_seen["content"], "42")

    def test_stops_at_max_steps(self):
        llm = FakeLLM([tool_call("get_current_time")] * 3)
        agent = Agent(llm, self.registry, max_steps=3)
        self.assertIn("Stopped after 3 steps", agent.run("loop forever"))

    def test_confirmation_can_deny(self):
        registry = ToolRegistry()

        @registry.register(requires_confirmation=True)
        def delete_everything() -> str:
            """Dangerous action."""
            return "deleted"

        llm = FakeLLM([tool_call("delete_everything"), answer("ok")])
        agent = Agent(llm, registry, confirm=lambda name, args: False)
        agent.run("clean up")
        self.assertIn("denied", llm.calls[1][-1]["content"])


if __name__ == "__main__":
    unittest.main()
