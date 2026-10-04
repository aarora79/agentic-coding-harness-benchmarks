"""Tests for the Strands runner's SDK-free helpers and argument checks.

The SDK is imported lazily inside the runner, so these run without the
optional ``strands`` dependency group installed.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import strands_agent_runner as runner  # noqa: E402


class UsageDictTest(unittest.TestCase):
    def test_missing_keys_default_to_zero(self) -> None:
        usage = runner._usage_dict({"inputTokens": 5})
        self.assertEqual(
            usage,
            {
                "inputTokens": 5,
                "outputTokens": 0,
                "totalTokens": 0,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": 0,
            },
        )

    def test_none_usage_is_all_zero(self) -> None:
        self.assertEqual(sum(runner._usage_dict(None).values()), 0)


class PreviewTest(unittest.TestCase):
    def test_long_value_is_truncated_to_one_line(self) -> None:
        text = runner._preview("a\n" * 500, limit=10)
        self.assertEqual(text, "a a a a a ...")


class ParseArgsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.skill_dir = Path(self._tmp.name)
        (self.skill_dir / "SKILL.md").write_text("---\nname: x\n---\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _args(self, *extra: str) -> list[str]:
        return [
            "--model",
            "m",
            "--skill-dir",
            str(self.skill_dir),
            "--prompt",
            "p",
            *extra,
        ]

    def test_bedrock_with_region_parses(self) -> None:
        args = runner._parse_args(
            self._args("--provider", "bedrock", "--aws-region", "us-east-1")
        )
        self.assertEqual(args.aws_region, "us-east-1")

    def test_endpoint_without_url_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            runner._parse_args(self._args("--provider", "endpoint"))

    def test_missing_skill_md_is_rejected(self) -> None:
        (self.skill_dir / "SKILL.md").unlink()
        with self.assertRaises(SystemExit):
            runner._parse_args(
                self._args("--provider", "endpoint", "--endpoint", "http://x")
            )


class _FakeOpenAIModel:
    """Stands in for strands.models.openai.OpenAIModel without the SDK."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def format_request(self, *args: object, **kwargs: object) -> dict:
        return {"model": "m", "tools": []}


class BuildEndpointModelTest(unittest.TestCase):
    """The endpoint branch, with the SDK module stubbed so no install is needed."""

    def _build(self, context_window: int) -> object:
        openai_module = mock.MagicMock()
        openai_module.OpenAIModel = _FakeOpenAIModel
        args = argparse.Namespace(
            provider="endpoint",
            endpoint="http://127.0.0.1:8000/",
            model="m",
            max_tokens=100,
            context_window=context_window,
        )
        with mock.patch.dict(sys.modules, {"strands.models.openai": openai_module}):
            return runner._build_model(args)

    def test_known_window_leaves_room_for_the_output(self) -> None:
        # vLLM counts max_tokens (100 here) against the window.
        model = self._build(context_window=131072)
        self.assertEqual(model.kwargs["context_window_limit"], 131072 - 100)

    def test_unknown_window_leaves_sdk_default(self) -> None:
        model = self._build(context_window=0)
        self.assertNotIn("context_window_limit", model.kwargs)

    def test_request_without_tools_omits_tools_key(self) -> None:
        model = self._build(context_window=0)
        self.assertNotIn("tools", model.format_request([]))


class SystemPromptToolMapTest(unittest.TestCase):
    def test_every_tool_the_skill_names_is_mapped(self) -> None:
        # swe3/SKILL.md names these Claude Code tools (issue #202).
        for name in ("Read", "Edit", "Write", "Bash", "Grep", "Glob", "Task"):
            with self.subTest(tool=name):
                self.assertIn(f"{name}", runner.SYSTEM_PROMPT)

    def test_map_names_only_the_two_real_tools(self) -> None:
        self.assertIn("exactly two tools: file_editor and shell", runner.SYSTEM_PROMPT)


class PromptWithSkillTest(unittest.TestCase):
    def test_skill_text_comes_before_the_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("SKILL BODY", encoding="utf-8")
            prompt = runner._prompt_with_skill(skill_dir, "TASK")
        self.assertEqual(
            prompt,
            "SKILL BODY\n\n---\n\n"
            "Follow the skill instructions above to complete the following task.\n\n"
            "TASK",
        )


class DropEmptyToolsTest(unittest.TestCase):
    def test_empty_list_is_removed(self) -> None:
        self.assertEqual(
            runner._drop_empty_tools({"tools": [], "model": "m"}), {"model": "m"}
        )

    def test_non_empty_list_is_kept(self) -> None:
        request = {"tools": [{"type": "function"}]}
        self.assertEqual(runner._drop_empty_tools(request), request)


class CapToolResultTest(unittest.TestCase):
    def _result(self, *blocks: dict) -> dict:
        return {"toolUseId": "t1", "status": "success", "content": list(blocks)}

    def test_small_result_is_unchanged(self) -> None:
        result = self._result({"text": "abc"})
        self.assertEqual(runner._cap_tool_result(result, limit=10), (result, 0))

    def test_large_text_is_cut_to_the_limit(self) -> None:
        capped, total = runner._cap_tool_result(
            self._result({"text": "x" * 50}), limit=10
        )
        self.assertTrue(
            capped["content"][0]["text"].startswith("x" * 10 + "\n\n[Output truncated")
        )
        self.assertEqual(total, 50)

    def test_large_json_block_is_counted_and_cut(self) -> None:
        result = self._result({"json": {"output": "y" * 50, "exit_code": 0}})
        capped, total = runner._cap_tool_result(result, limit=10)
        self.assertGreater(total, 50)
        self.assertEqual(capped["status"], "success")
        self.assertEqual(capped["toolUseId"], "t1")


if __name__ == "__main__":
    unittest.main()
