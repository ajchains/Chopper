"""
All Pydantic models for the pipeline, one per phase output, plus the shared
primitives they're built from. Ported from the original monolith's "Output
Models" section — no behavior changes, just relocated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from pathlib import Path
from typing import Dict

categories = [
    "code",
    "refactoring",
    "testing",
    "data_processing",
    "data_analysis",
    "machine_learning",
    "ai_agent",
    "writing",
    "documentation",
    "technical_writing",
    "ui_ux",
    "frontend",
    "backend",
    "fullstack",
    "devops",
    "database",
    "security",
    "math",
]

categories_for_prompt = "- " + "\n- ".join(categories)

Category = Literal[*categories]

ArtifactType = Literal[
    "class",
    "function",
    "constant",
    "api_route",
    "model",
    "schema",
    "config",
    "interface",
]

FileMode = Literal["w", "a"]
ComplianceStatus = Literal["COMPLIANT", "NON_COMPLIANT", "PARTIAL"]
OverallStatus = Literal["PASS", "FAIL"]



# ══════════════════════════════════════════════════════════════════════════
# Shared Primitives
# ══════════════════════════════════════════════════════════════════════════


class OutputFile(BaseModel):
    path: str = Field(
        ...,
        description="File path relative to project root. Must be a file, not a directory.",
    )
    mode: FileMode = Field(..., description="'w' = create new file, 'a' = append to existing")
    format: str = Field(
        ...,
        description="Output format: 'python', 'typescript', 'json', 'markdown', etc.",
    )


class TaskDependency(BaseModel):
    task_id: str
    dependencies: list[str]


class TaskIssue(BaseModel):
    """Reused for missing / unnecessary / overlapping task references."""

    task_id: str
    reason: str


class MissingTask(BaseModel):
    task_name: str
    reason: str


class AttributeParam(BaseModel):
    """A single parameter, field, or attribute in a formal definition."""

    name: str
    type: str
    description: str
    required: bool = True


# ── Core task node — shared by Phase 1, 3, and 5 ────────────────────────────


class Task(BaseModel):
    task_id: str
    task_name: str
    primary_category: Category
    task_categories: list[Category]
    objective: str = Field(..., description="Single, clear responsibility of this task")
    scope: list[str]
    out_of_scope: list[str]
    expected_deliverable: str
    output_file: OutputFile
    dependencies: list[TaskDependency] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Phase 1 — Planner Agent
# ══════════════════════════════════════════════════════════════════════════


class PlannerOutput(BaseModel):
    """Output of the Planner Agent (Phase 1). Initial task DAG."""

    project_summary: str
    decomposition_strategy: str = Field(
        ..., description="Brief explanation of how the project was decomposed"
    )
    dag: dict[str, Task] = Field(..., description="Keys are task IDs (e.g. 'T-001')")


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 — DAG Verification Agent
# ══════════════════════════════════════════════════════════════════════════


class VerificationOutput(BaseModel):
    """One instance produced per task being reviewed."""

    task_id: str
    dag_valid_for_task: bool
    summary: str
    issues: list[str] = Field(default_factory=list)
    missing_dependencies: list[TaskIssue] = Field(default_factory=list)
    unnecessary_dependencies: list[TaskIssue] = Field(default_factory=list)
    missing_tasks: list[MissingTask] = Field(default_factory=list)
    overlapping_tasks: list[TaskIssue] = Field(default_factory=list)
    scope_corrections: list[str] = Field(default_factory=list)
    output_file_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns about this task's output_file path, mode, or format",
    )
    suggested_dag_changes: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Phase 3 — Validation Agent
# ══════════════════════════════════════════════════════════════════════════


class RejectedChange(BaseModel):
    change: str
    reason: str


class OutputFileResolution(BaseModel):
    task_id: str
    concern: str
    resolution: str


class ValidationOutput(BaseModel):
    """Canonical, verified final DAG."""

    project_summary: str
    validation_summary: str
    accepted_changes: list[str] = Field(default_factory=list)
    rejected_changes: list[RejectedChange] = Field(default_factory=list)
    output_file_resolutions: list[OutputFileResolution] = Field(default_factory=list)
    final_dag: dict[str, Task] = Field(
        ..., description="Canonical DAG after resolving all verification reports"
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 4 — Dependency Specification Agent
# ══════════════════════════════════════════════════════════════════════════


class ConsumedFormalDefinition(BaseModel):
    """Exact specification of an artifact this task consumes from a dependency."""

    file_location: str = Field(..., description="Exact path where the artifact lives")
    import_statement: str = Field(..., description="Exact, valid import statement")
    signature_or_schema: str = Field(..., description="Complete, type-annotated definition")
    attributes_or_parameters: list[AttributeParam] = Field(default_factory=list)
    return_type: str | None = None
    description: str


class ProducedFormalDefinition(BaseModel):
    """Exact specification of an artifact this task produces for consumers."""

    file_location: str = Field(..., description="Must match this task's output_file.path")
    export_statement: str = Field(
        ..., description="The definition as it will appear in the file"
    )
    signature_or_schema: str = Field(..., description="Complete, type-annotated definition")
    attributes_or_parameters: list[AttributeParam] = Field(default_factory=list)
    return_type: str | None = None
    description: str


class DependencySpec(BaseModel):
    """What this task consumes from one specific upstream task."""

    depends_on_task_id: str
    dependency_name: str = Field(
        ..., description="Exact class / function / constant name — no prose"
    )
    purpose: str
    required_artifact_type: ArtifactType
    formal_definition: ConsumedFormalDefinition
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    example: str | None = Field(default=None, description="Valid code snippet, not prose")


class ProducesSpec(BaseModel):
    """What this task produces for downstream consumers."""

    artifact_name: str = Field(..., description="Exact name as it will appear in the output file")
    purpose: str
    artifact_type: ArtifactType
    formal_definition: ProducedFormalDefinition
    constraints: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)


class DependencySpecOutput(BaseModel):
    """One instance per task."""

    task_id: str
    dependency_specifications: list[DependencySpec] = Field(default_factory=list)
    produces_specifications: list[ProducesSpec] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Phase 5 — Dependency Coordinator Agent
# ══════════════════════════════════════════════════════════════════════════


class ResolvedConflict(BaseModel):
    dependency_name: str
    conflicting_tasks: list[str]
    resolution: str = Field(..., description="How and why the conflict was resolved")


class CanonicalDefinition(BaseModel):
    file_location: str = Field(
        ..., description="Canonical path matching the producer's finalized output_file.path"
    )
    import_statement: str | None = Field(
        default=None, description="Canonical import for same-language consumers"
    )
    neutral: str = Field(
        ...,
        description=(
            "Language-agnostic definition: JSON Schema fragment, "
            "OpenAPI fragment, or typed pseudocode"
        ),
    )
    representations: dict[str, str] = Field(
        ..., description="format → complete language-specific definition"
    )
    signature_or_schema: str = Field(..., description="Final canonical, type-annotated definition")
    attributes_or_parameters: list[AttributeParam] = Field(default_factory=list)
    return_type: str | None = None


class DependencyContract(BaseModel):
    """Single canonical contract for one shared artifact."""

    dependency_id: str = Field(..., description="e.g. 'D-001'")
    dependency_name: str
    producer_tasks: list[str]
    consumer_tasks: list[str]
    artifact_type: ArtifactType
    canonical_definition: CanonicalDefinition
    constraints: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class CoordinatorOutput(BaseModel):
    """Single source of truth consumed by all Executor agents."""

    integration_summary: str
    resolved_conflicts: list[ResolvedConflict] = Field(default_factory=list)
    dependency_contracts: list[DependencyContract] = Field(
        ..., description="One contract per shared artifact across the project"
    )
    dag: dict[str, Task] = Field(..., description="Finalized DAG with canonicalized output_file.path")


# ══════════════════════════════════════════════════════════════════════════
# Phase 6 — Executor Agent
# ══════════════════════════════════════════════════════════════════════════


class ContractComplianceItem(BaseModel):
    dependency_id: str
    status: ComplianceStatus
    notes: str = Field(..., description="How the contract was followed or why it was not")


class SelfVerification(BaseModel):
    objective_completed: bool
    scope_respected: bool
    deliverable_produced: bool
    contract_followed: bool
    output_file_correct: bool


class ExecutorOutput(BaseModel):
    """One instance per implemented task."""

    task_id: str
    task_summary: str
    assumptions: list[str] = Field(default_factory=list)
    output_file: OutputFile = Field(..., description="Must exactly match the contract's output_file spec")
    implementation: str = Field(
        ...,
        description=(
            "Complete, ready-to-write file content. "
            "Every contract-specified name must appear verbatim."
        ),
    )
    contract_compliance: list[ContractComplianceItem] = Field(default_factory=list)
    self_verification: SelfVerification


# ══════════════════════════════════════════════════════════════════════════
# Phase 7 — Evaluator Agent
# ══════════════════════════════════════════════════════════════════════════

class EvaluatorOutput(BaseModel):
    """Bruh"""
    



output_models: dict[str, type[BaseModel]] = {
    "planner": PlannerOutput,
    "dag_verification": VerificationOutput,
    "dag_validation": ValidationOutput,
    "dependency_resolution": DependencySpecOutput,
    "coordinator": CoordinatorOutput,
    "executor": ExecutorOutput,
    "evaluator": EvaluatorOutput,
}

def serializer(obj):
    """JSON fallback for Pydantic models and other non-serializable types."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")