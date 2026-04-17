"""Workflow primitives for the LEAM desktop application."""

from .models import (
    ArtifactRef,
    AttachmentRef,
    IssueRefill,
    StepResult,
    WorkflowSession,
    WorkflowStepDefinition,
    WorkflowStepState,
)

__all__ = [
    "ArtifactRef",
    "AttachmentRef",
    "IssueRefill",
    "StepResult",
    "WorkflowSession",
    "WorkflowStepDefinition",
    "WorkflowStepState",
    "WorkflowEngine",
]


def __getattr__(name: str):
    if name == "WorkflowEngine":
        from .engine import WorkflowEngine

        return WorkflowEngine
    raise AttributeError(name)
