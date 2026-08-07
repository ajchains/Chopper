"""Pipeline State TypedDict and its default-value factory."""

from __future__ import annotations

from typing import Dict, TypedDict

from schemas import (
    DependencyContract,
    DependencySpecOutput,
    EvaluatorOutput,
    ExecutorOutput,
    OutputFileResolution,
    RejectedChange,
    DependencyConflictResolution,
    Task,
    VerificationOutput,
    ParallelismAnalysis,
)

DEFAULT_POOL = 8


class State(TypedDict):
    question: str
    prompt: str
    phase: str

    # Phase 1 — Planner
    project_summary: str
    decomposition_strategy: str
    dag: Dict[str, Task]
    parallelism_analysis: ParallelismAnalysis | None = None
    total_tasks: int

    # Phase 2 — DAG Verification (parallel fan-out, one agent per task)
    changes: list[VerificationOutput]
    changes_required: int

    # Phase 3 — Validation
    validation_summary: str
    accepted_changes: list[str]
    rejected_changes: list[RejectedChange]
    output_file_resolutions: list[OutputFileResolution]
    # dag is overwritten here with ValidationOutput.final_dag

    # Phase 4 — Dependency Specification (parallel fan-out, one agent per task)
    dependency_specs: list[DependencySpecOutput]

    # Phase 5 — Dependency Coordinator
    integration_summary: str
    resolved_conflicts: list[DependencyConflictResolution]
    dependency_contracts: list[DependencyContract]
    # dag is overwritten here with CoordinatorOutput.dag (canonicalized paths)

    # Phase 6 — Executor (parallel fan-out)
    implementations: list[ExecutorOutput]

    # Phase 7 — Evaluator (parallel fan-out)
    evaluations: list[EvaluatorOutput]

    # Aggregate evaluation metrics (computed after Phase 7 fan-in)
    passed_tasks: int
    failed_tasks: int
    average_score: float
    average_objective_score: float
    average_scope_score: float
    average_naming_score: float
    average_contract_score: float
    average_quality_score: float
    integration_readiness_pct: int
    blocking_issues: list[str]
    required_fixes: list[str]
    recommendations: list[str]

    # Fan-out concurrency control
    #pool: int


def default_state() -> dict:
    """
    Single source of truth for the dict shape passed to `app.ainvoke`.
    Field-for-field match against `State` — verified by a smoke test
    (see tests in this package) so the two can't silently drift apart again.
    """
    return {
        "question": "",
        "prompt": "",
        "phase": "",
        "project_summary": "",
        "decomposition_strategy": "",
        "dag": {},
        "parallelism_analysis": None,
        "total_tasks": 0,
        "changes": [],
        "changes_required": 0,
        "validation_summary": "",
        "accepted_changes": [],
        "rejected_changes": [],
        "output_file_resolutions": [],
        "dependency_specs": [],
        "integration_summary": "",
        "resolved_conflicts": [],
        "dependency_contracts": [],
        "implementations": [],
        "evaluations": [],
        "passed_tasks": 0,
        "failed_tasks": 0,
        "average_score": 0.0,
        "average_objective_score": 0.0,
        "average_scope_score": 0.0,
        "average_naming_score": 0.0,
        "average_contract_score": 0.0,
        "average_quality_score": 0.0,
        "integration_readiness_pct": 0,
        "blocking_issues": [],
        "required_fixes": [],
        "recommendations": [],
        #"pool": DEFAULT_POOL,
    }