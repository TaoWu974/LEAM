import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.core.errors import InputValidationError, LlmCallError
from leam.core.llm_caller import LLMCaller
from leam.utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT


class LLMCallerResponsesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ensure_key_patcher = patch(
            "leam.core.llm_caller.ensure_openai_api_key",
            return_value="test-key",
        )
        self.load_config_patcher = patch(
            "leam.core.llm_caller.load_config",
            return_value={},
        )
        self.openai_patcher = patch("leam.core.llm_caller.openai.OpenAI")

        self.ensure_key_patcher.start()
        self.load_config_patcher.start()
        self.mock_openai_cls = self.openai_patcher.start()
        self.mock_client = MagicMock()
        self.mock_openai_cls.return_value = self.mock_client

    def tearDown(self) -> None:
        self.openai_patcher.stop()
        self.load_config_patcher.stop()
        self.ensure_key_patcher.stop()

    def _write_prompt(self, content: str = "prompt") -> str:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def _write_text_file(
        self,
        content: str = "prompt",
        suffix: str = ".txt",
    ) -> str:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def _write_image(self, suffix: str = ".png") -> str:
        tmp = tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False)
        tmp.write(b"\x89PNG\r\n\x1a\n")
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def _write_pdf(self) -> str:
        tmp = tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False)
        tmp.write(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_responses_request_format_and_reasoning_mapping(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL, reasoning_effort="high")

        result = caller.call_llm(
            prompt_files=[self._write_prompt("hello prompt")],
            description="extra context",
            image_paths=[self._write_image()],
        )

        self.assertEqual(result, "ok")
        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], DEFAULT_MODEL)
        self.assertIn("hello prompt", kwargs["instructions"])
        self.assertEqual(kwargs["reasoning"], {"effort": "high"})
        self.assertNotIn("messages", kwargs)

        input_payload = kwargs["input"]
        self.assertEqual(input_payload[0]["role"], "user")
        content = input_payload[0]["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[0]["text"], "extra context")
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "auto")
        self.assertTrue(content[1]["image_url"].startswith("data:image/"))

    def test_pdf_inputs_use_input_file_blocks(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)
        pdf_path = self._write_pdf()

        caller.call_llm(
            prompt_files=[self._write_prompt("system prompt")],
            description="user input",
            pdf_paths=[pdf_path],
        )

        kwargs = self.mock_client.responses.create.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "user input"})
        self.assertEqual(content[1]["type"], "input_file")
        self.assertEqual(content[1]["filename"], Path(pdf_path).name)
        self.assertTrue(content[1]["file_data"])

    def test_prompt_instructions_only_include_prompt_basename(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)
        prompt_path = self._write_prompt("system prompt")

        caller.call_llm(
            prompt_files=[prompt_path],
            description="user input",
        )

        instructions = self.mock_client.responses.create.call_args.kwargs["instructions"]
        self.assertIn(Path(prompt_path).name, instructions)
        self.assertNotIn(prompt_path, instructions)

    def test_text_only_calls_use_instructions_and_string_content(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)

        caller.call_llm(
            prompt_files=[self._write_prompt("system prompt")],
            description="user input",
        )

        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertIn("system prompt", kwargs["instructions"])
        self.assertEqual(
            kwargs["input"],
            [{"role": "user", "content": "user input"}],
        )
        self.assertEqual(
            kwargs["reasoning"],
            {"effort": DEFAULT_REASONING_EFFORT},
        )

    def test_unknown_text_suffix_can_be_used_as_prompt_file(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)

        caller.call_llm(
            prompt_files=[self._write_text_file("material prompt", ".mtd")],
        )

        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["input"][0]["role"], "user")
        self.assertIn("material prompt", kwargs["input"][0]["content"])

    def test_openai_timeout_is_passed_to_client_and_request(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )

        with patch(
            "leam.core.llm_caller.resolve_openai_timeout_seconds",
            return_value=123.0,
        ):
            caller = LLMCaller(default_model=DEFAULT_MODEL)

        self.mock_openai_cls.assert_called_with(
            api_key="test-key",
            timeout=123.0,
        )

        caller.call_llm(prompt_files=[self._write_prompt("prompt")])

        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 123.0)

    def test_json_object_requests_include_json_keyword_in_user_input(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="{}"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)

        caller.call_llm(
            prompt_files=[self._write_prompt("system prompt")],
            description="user input",
            text_format={"type": "json_object"},
        )

        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertIn("system prompt", kwargs["instructions"])
        self.assertIn("json", kwargs["input"][0]["content"].lower())
        self.assertIn("user input", kwargs["input"][0]["content"])

    def test_default_tools_are_passed_to_responses_api(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="ok"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)
        tools = [
            {"type": "code_interpreter", "container": {"type": "auto"}}
        ]
        caller.set_default_tools(tools)
        caller.set_default_tool_choice("auto")

        caller.call_llm(prompt_files=[self._write_prompt("prompt only")])

        kwargs = self.mock_client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["tools"], tools)
        self.assertEqual(kwargs["tool_choice"], "auto")
        self.assertNotIn("instructions", kwargs)
        self.assertEqual(kwargs["input"][0]["role"], "user")
        self.assertIn("prompt only", kwargs["input"][0]["content"])

    def test_empty_output_text_raises_error(self) -> None:
        self.mock_client.responses.create.return_value = SimpleNamespace(
            output_text="   "
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)

        with self.assertRaises(LlmCallError):
            caller.call_llm(prompt_files=[self._write_prompt("prompt")])

    def test_tool_error_strict_failure_without_retry(self) -> None:
        self.mock_client.responses.create.side_effect = RuntimeError(
            "code_interpreter unsupported"
        )
        caller = LLMCaller(default_model=DEFAULT_MODEL)
        caller.set_default_tools(
            [{"type": "code_interpreter", "container": {"type": "auto"}}]
        )
        caller.set_default_tool_choice("auto")

        with self.assertRaises(LlmCallError):
            caller.call_llm(prompt_files=[self._write_prompt("prompt")])
        self.assertEqual(self.mock_client.responses.create.call_count, 1)

    def test_unsupported_image_extensions_are_rejected(self) -> None:
        caller = LLMCaller(default_model=DEFAULT_MODEL)

        with self.assertRaises(InputValidationError):
            caller.call_llm(
                prompt_files=[self._write_prompt("prompt")],
                image_paths=[self._write_image(".gif")],
            )


if __name__ == "__main__":
    unittest.main()
