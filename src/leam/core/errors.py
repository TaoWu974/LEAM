"""Shared exception hierarchy for LEAM core generation workflows."""


class LeamError(Exception):
    """Base exception for LEAM core errors."""


class InputValidationError(LeamError, ValueError):
    """Raised when required inputs are invalid or missing."""


class LlmCallError(LeamError):
    """Raised when an LLM call fails or returns unusable output."""


class GenerationError(LeamError):
    """Raised when script/macro generation fails."""
