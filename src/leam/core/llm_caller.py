"""Unified LLM caller built on the current OpenAI Responses API."""

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import openai

from ..config import (
    ensure_openai_api_key,
    load_config,
    resolve_openai_timeout_seconds,
)
from ..utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from ..utils.document_utils import encode_pdfs_for_responses
from ..utils.file_io import process_text_files
from ..utils.image_utils import encode_images_for_responses
from .errors import InputValidationError, LlmCallError


class LLMCaller:
    """Low-level wrapper that standardizes LEAM requests to Responses API."""

    def __init__(
        self,
        default_model: str = DEFAULT_MODEL,
        reasoning_effort: Optional[str] = DEFAULT_REASONING_EFFORT,
    ):
        """Initialize OpenAI client and per-instance default request options."""
        config = load_config()
        api_key = ensure_openai_api_key()
        self.timeout_seconds = resolve_openai_timeout_seconds(config)
        self.client = openai.OpenAI(
            api_key=api_key,
            timeout=self.timeout_seconds,
        )
        self.default_model = default_model
        self.reasoning_effort = reasoning_effort
        self.default_tools: Optional[List[dict]] = None
        self.default_tool_choice: Optional[Any] = None

    def _build_request_input(
        self,
        prompt_text: str,
        description: Optional[str],
        image_paths: Optional[List[str]],
        pdf_paths: Optional[List[str]],
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Build `instructions` plus `input` payload for a Responses request.

        Current API guidance uses top-level `instructions` for system/developer
        prompts, plain string message content for text-only user turns, and
        structured `input_text`/`input_image` parts for multimodal turns.
        """
        user_text = str(description).strip() if description else ""

        if image_paths or pdf_paths:
            content: List[Dict[str, Any]] = []
            if user_text:
                content.append({"type": "input_text", "text": user_text})
            if pdf_paths:
                content.extend(encode_pdfs_for_responses(pdf_paths))
            if image_paths:
                content.extend(encode_images_for_responses(image_paths))
            return prompt_text, [{"role": "user", "content": content}]

        if user_text:
            return prompt_text, [{"role": "user", "content": user_text}]

        # Keep prompt-only calls working without fabricating user text.
        return None, [{"role": "user", "content": prompt_text}]

    @staticmethod
    def _requires_json_input_hint(text_format: Optional[dict]) -> bool:
        """Return True when the request uses a JSON-constrained text format."""
        if not isinstance(text_format, dict):
            return False
        return str(text_format.get("type") or "").lower() in {
            "json_object",
            "json_schema",
        }

    def _ensure_json_keyword_in_input(
        self,
        input_payload: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Ensure at least one user input item mentions JSON for Responses API."""
        if not input_payload:
            return input_payload

        payload = deepcopy(input_payload)
        user_message = payload[0]
        content = user_message.get("content")

        if isinstance(content, str):
            if "json" not in content.lower():
                user_message["content"] = (
                    "Return the answer in JSON.\n\n"
                    f"{content}"
                ).strip()
            return payload

        if isinstance(content, list):
            for item in content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "input_text"
                    and "json" in str(item.get("text") or "").lower()
                ):
                    return payload

            content.insert(0, {"type": "input_text", "text": "Return JSON."})

        return payload

    def set_default_tools(self, tools: Optional[List[dict]]) -> None:
        """Set default tool declarations for Responses API calls."""
        self.default_tools = deepcopy(tools) if tools else None

    def set_default_tool_choice(self, tool_choice: Optional[Any]) -> None:
        """Set default tool choice for Responses API calls."""
        if tool_choice is None:
            self.default_tool_choice = None
            return
        self.default_tool_choice = deepcopy(tool_choice)

    def _format_api_error(self, exc: Exception) -> str:
        """Return a concise error string with upstream API details when present."""
        if isinstance(exc, openai.APITimeoutError):
            return (
                "OpenAI API request timed out "
                f"after {self.timeout_seconds:.0f} seconds."
            )

        if isinstance(exc, openai.APIStatusError):
            parts = [f"OpenAI API {exc.status_code}: {exc.message}"]
            if exc.request_id:
                parts.append(f"request_id={exc.request_id}")
            if exc.param:
                parts.append(f"param={exc.param}")
            if exc.code:
                parts.append(f"code={exc.code}")
            if exc.body is not None:
                try:
                    body = json.dumps(exc.body, ensure_ascii=False)
                except TypeError:
                    body = str(exc.body)
                parts.append(f"body={body}")
            return " | ".join(parts)

        if isinstance(exc, openai.APIError):
            parts = [f"OpenAI API error: {exc.message}"]
            if exc.param:
                parts.append(f"param={exc.param}")
            if exc.code:
                parts.append(f"code={exc.code}")
            if exc.body is not None:
                try:
                    body = json.dumps(exc.body, ensure_ascii=False)
                except TypeError:
                    body = str(exc.body)
                parts.append(f"body={body}")
            return " | ".join(parts)

        return str(exc)

    def call_llm(
        self,
        prompt_files: List[str],
        model: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        description: Optional[str] = None,
        json_schema_hint: Optional[str] = None,
        text_format: Optional[dict] = None,
        reasoning_effort: Optional[str] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Call Responses API once and return non-empty `output_text`.

        Raises:
            InputValidationError: If no prompt files are provided.
            LlmCallError: If API call fails or returns empty text.
        """
        if not prompt_files:
            raise InputValidationError(
                "prompt_files must contain at least one prompt path."
            )

        prompt = process_text_files(prompt_files)
        if json_schema_hint:
            prompt = (
                f"{prompt}\n\n"
                "You must return valid JSON that follows this schema. "
                "Respond with JSON only, no prose.\n"
                f"{json_schema_hint}"
            )
        instructions, input_payload = self._build_request_input(
            prompt,
            description,
            image_paths,
            pdf_paths,
        )
        if self._requires_json_input_hint(text_format):
            input_payload = self._ensure_json_keyword_in_input(input_payload)

        effort = (
            reasoning_effort
            if reasoning_effort is not None
            else self.reasoning_effort
        )
        response_args: Dict[str, Any] = {
            "model": model or self.default_model,
            "input": input_payload,
        }
        if instructions:
            response_args["instructions"] = instructions
        if effort:
            # Responses API accepts reasoning options under the `reasoning` key.
            response_args["reasoning"] = {"effort": effort}
        if self.default_tools:
            response_args["tools"] = deepcopy(self.default_tools)
        if self.default_tool_choice is not None:
            response_args["tool_choice"] = deepcopy(self.default_tool_choice)
        if text_format is not None:
            response_args["text"] = {"format": deepcopy(text_format)}
        response_args["timeout"] = self.timeout_seconds

        try:
            response = self.client.responses.create(**response_args)
        except Exception as exc:
            detail = self._format_api_error(exc)
            raise LlmCallError(
                f"Failed to call LLM via Responses API. {detail}"
            ) from exc

        # `output_text` is the canonical flattened text accessor on Responses.
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        raise LlmCallError("LLM returned empty output_text.")
