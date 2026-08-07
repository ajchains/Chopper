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

TaskCategory = Literal[
    "backend",
    "frontend",
    "database",
    "api",
    "security",
    "testing",
    "infrastructure",
    "documentation",
    "configuration",
    "monitoring",
    "ml",
    "integration",
]

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
ContractStatus = Literal["COMPLIANT", "NON_COMPLIANT"]
OverallStatus = Literal["PASS", "FAIL"]

VerificationIssueType = Literal[
    "missing_dependency",
    "scope_overlap",
    "missing_task",
    "redundant_task",
    "poor_sequencing",
]


# ══════════════════════════════════════════════════════════════════════════
# Shared Primitives
# ══════════════════════════════════════════════════════════════════════════


class OutputFile(BaseModel):
    """
    Describes the single file artifact a task must produce.
    Every task produces exactly one OutputFile.
    """

    path: str = Field(
        ...,
        description=(
            "File path relative to project root. "
            "Must be a file with extension — not a directory. "
            "Example: 'src/services/user_service.py', not 'src/services/'."
        ),
    )
    mode: FileMode = Field(
        ...,
        description="'w' = create new file. 'a' = append to existing file.",
    )
    format: str = Field(
        ...,
        description=(
            "Output format of the file. "
            "Examples: 'python', 'typescript', 'json', 'markdown', 'yaml', "
            "'sql', 'bash', 'dockerfile', 'terraform', 'go', 'rust'."
        ),
    )

    @model_validator(mode="after")
    def path_must_be_file(self) -> "OutputFile":
        if not self.path or self.path.endswith("/"):
            raise ValueError(
                f"output_file.path must be a file path, not a directory. Got: '{self.path}'"
            )
        # if "." not in self.path.rsplit("/", 1)[-1]:
        #     raise ValueError(
        #         f"output_file.path must include a file extension. Got: '{self.path}'"
        #     )
        return self


class TaskDependency(BaseModel):
    task_id: str
    dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "All artifacts or dependencies of task_id tasks the original task depends on. "
            "A dependency exists only when one task cannot execute correctly "
            "without the artifact produced by other task. "
            "Empty list if no dependencies on this task_id."
            "Do ont use file paths for dependencies. Explain what dependency exist."
        ),
    )


class TaskIssue(BaseModel):
    """Reused for missing / unnecessary / overlapping task references."""

    task_id: str
    reason: str


class MissingTask(BaseModel):
    task_name: str
    reason: str


def _compute_ancestors(dag: dict[str, Task]) -> dict[str, set[str]]:
    """
    For every task, compute the full set of transitive dependencies
    (its ancestors in the DAG). Memoized DFS.

    Assumes the graph is already known to be acyclic — call only after
    a cycle check has passed, or this will recurse infinitely on a cycle.
    """
    ancestors: dict[str, set[str]] = {}

    def dfs(task_id: str) -> set[str]:
        if task_id in ancestors:
            return ancestors[task_id]

        task = dag.get(task_id)
        if task is None:
            ancestors[task_id] = set()
            return ancestors[task_id]

        result: set[str] = set()
        for dep in task.dependencies:
            dep_id = dep.task_id
            result.add(dep_id)
            result |= dfs(dep_id)

        ancestors[task_id] = result
        return result

    for task_id in dag:
        dfs(task_id)

    return ancestors


class SharedPathViolation(ValueError):
    """Raised when a shared output_file.path fails the write/append validity rule."""


def _validate_shared_output_paths(dag: dict[str, Task]) -> None:
    """
    A path may be shared by multiple tasks only as a valid create-then-append
    chain: exactly one 'w' owner, all others 'a', every appender transitively
    dependent on the owner, and every pair sharing the path — including two
    'a' tasks compared to each other, not just each vs. the owner —
    transitively ordered against one another. A shared ancestor alone is not
    sufficient: two appenders that both depend on the writer but not on each
    other can still be scheduled in parallel and race on the file.

    Raises SharedPathViolation on the first violation found. Call only after
    detect_cycle(dag) confirms the graph is acyclic.
    """
    ancestors = _compute_ancestors(dag)

    paths: dict[str, list[Task]] = {}
    for task in dag.values():
        paths.setdefault(task.output_file.path, []).append(task)

    for path, tasks in paths.items():
        if len(tasks) < 2:
            continue

        writers = [t for t in tasks if t.output_file.mode == "w"]
        appenders = [t for t in tasks if t.output_file.mode == "a"]
        unsupported = [t for t in tasks if t.output_file.mode not in ("w", "a")]

        if unsupported:
            raise SharedPathViolation(
                f"output_file.path '{path}' is shared by task(s) "
                f"{[t.task_id for t in unsupported]} with an unsupported mode."
            )
        if len(writers) != 1:
            raise SharedPathViolation(
                f"output_file.path '{path}' must have exactly one task with "
                f"mode 'w'. Found {len(writers)}: {[t.task_id for t in writers]}."
            )

        owner = writers[0]

        for appender in appenders:
            if owner.task_id not in ancestors.get(appender.task_id, set()):
                raise SharedPathViolation(
                    f"Task '{appender.task_id}' appends to output_file.path "
                    f"'{path}' but has no direct or transitive dependency on "
                    f"its owner '{owner.task_id}'."
                )

        for i, task_a in enumerate(appenders):
            for task_b in appenders[i + 1:]:
                a_ancestors = ancestors.get(task_a.task_id, set())
                b_ancestors = ancestors.get(task_b.task_id, set())
                ordered = task_b.task_id in a_ancestors or task_a.task_id in b_ancestors
                if not ordered:
                    raise SharedPathViolation(
                        f"Tasks '{task_a.task_id}' and '{task_b.task_id}' both "
                        f"append to output_file.path '{path}' but neither "
                        f"depends on the other — they can run in parallel "
                        f"and race on the file."
                    )

def _detect_cycle(dag: dict[str, Task]) -> str | None:
    """
    Returns a human-readable description of the first cycle found
    (e.g. "T-001 -> T-002 -> T-001"), or None if the DAG is acyclic.

    Extracted here so ValidationAgentOutput.validate_no_cycles and
    FinalDependencyContract.validate_no_cycles both call this instead of
    each maintaining their own copy of the same DFS.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {tid: WHITE for tid in dag}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        color[node] = GRAY
        path = path + [node]
        for dep in dag[node].dependencies:
            dep_id = dep.task_id
            if dep_id not in color:
                continue
            if color[dep_id] == GRAY:
                return path[path.index(dep_id):] + [dep_id]
            if color[dep_id] == WHITE:
                result = dfs(dep_id, path)
                if result is not None:
                    return result
        color[node] = BLACK
        return None

    for tid in dag:
        if color[tid] == WHITE:
            cycle = dfs(tid, [])
            if cycle is not None:
                return " -> ".join(cycle)
    return None

class ParallelExecutionLevel(BaseModel):
    """
    A set of tasks that can execute simultaneously —
    all their dependencies are satisfied by prior levels.
    """

    level: int = Field(
        ...,
        ge=1,
        description="Level number. Level 1 = tasks with no dependencies.",
    )
    task_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Task IDs executable at this level.",
    )
    description: str = Field(
        ...,
        description=(
            "What this level accomplishes. "
            "E.g., 'Level 1: Foundation — shared abstractions and project configuration'."
        ),
    )


class ParallelismAnalysis(BaseModel):
    """Structural analysis of the DAG's parallelism properties."""

    critical_path_length: int = Field(
        ...,
        ge=1,
        description=(
            "Number of sequential execution levels from start to last task. "
            "Lower is better."
        ),
    )
    max_parallel_tasks: int = Field(
        ...,
        ge=1,
        description="Maximum number of tasks executable simultaneously at any single level.",
    )
    parallel_execution_levels: list[ParallelExecutionLevel] = Field(
        ...,
        min_length=1,
        description=(
            "All execution levels in order. "
            "Level N tasks depend only on tasks in levels 1 through N-1."
        ),
    )

    @model_validator(mode="after")
    def validate_level_numbers_sequential(self) -> "ParallelismAnalysis":
        levels = sorted(lvl.level for lvl in self.parallel_execution_levels)
        expected = list(range(1, len(levels) + 1))
        if levels != expected:
            raise ValueError(
                f"Parallel execution levels must be sequential starting from 1. "
                f"Got: {levels}"
            )
        return self

    @model_validator(mode="after")
    def validate_critical_path_matches_levels(self) -> "ParallelismAnalysis":
        if self.critical_path_length != len(self.parallel_execution_levels):
            raise ValueError(
                f"critical_path_length ({self.critical_path_length}) must equal "
                f"the number of parallel_execution_levels ({len(self.parallel_execution_levels)})."
            )
        return self

def compute_parallelism_analysis(dag: dict[str, Task]) -> dict:
    """
    Code-computed execution levels — never delegated to an agent.

    Longest-path leveling: a task's level is 1 + max(level of its
    dependencies), or 1 if it has none. Tasks sharing a level have no
    ordering constraint between them and can run concurrently.

    Returns a plain dict shaped like the ParallelismAnalysis /
    ParallelExecutionLevel schema (critical_path_length, max_parallel_tasks,
    parallel_execution_levels) without depending on those model classes
    directly, since they're defined in the DAG-planning phase, not here.
    Construct the actual Pydantic model from this dict at the call site.

    Call only on an acyclic graph — check detect_cycle(dag) is None first;
    this raises defensively if a cycle slipped through.
    """
    cycle = _detect_cycle(dag)
    if cycle is not None:
        raise ValueError(f"Cannot compute parallelism analysis — cycle detected: {cycle}")

    level: dict[str, int] = {}

    def compute_level(task_id: str) -> int:
        if task_id in level:
            return level[task_id]
        task = dag[task_id]
        if not task.dependencies:
            level[task_id] = 1
            return 1
        computed = 1 + max(compute_level(dep.task_id) for dep in task.dependencies)
        level[task_id] = computed
        return computed

    for tid in dag:
        compute_level(tid)

    levels_to_tasks: dict[int, list[str]] = {}
    for tid, lvl in level.items():
        levels_to_tasks.setdefault(lvl, []).append(tid)

    parallel_execution_levels = []
    for lvl in sorted(levels_to_tasks):
        task_ids = sorted(levels_to_tasks[lvl])
        descriptions = [f"{tid} ({dag[tid].task_name})" for tid in task_ids]
        parallel_execution_levels.append({
            "level": lvl,
            "task_ids": task_ids,
            "description": f"Level {lvl}: " + ", ".join(descriptions),
        })

    return {
        "critical_path_length": len(parallel_execution_levels),
        "max_parallel_tasks": max(len(v) for v in levels_to_tasks.values()),
        "parallel_execution_levels": parallel_execution_levels,
    }

# ── Core task node — shared by Phase 1, 3, and 5 ────────────────────────────


class Task(BaseModel):
    """
    Core task node in the DAG.
    Each task represents one implementation unit producing exactly one file.
    """

    task_id: str = Field(
        ...,
        description="Sequential identifier. Format: 'T-001', 'T-002', etc.",
    )
    task_name: str = Field(
        ...,
        description="Short, descriptive name for the task.",
    )
    primary_category: TaskCategory = Field(
        ...,
        description="The dominant category of work this task performs.",
    )
    task_categories: list[TaskCategory] = Field(
        ...,
        description="All categories that apply to this task.",
    )
    objective: str = Field(
        ...,
        description=(
            "Single, clear responsibility of this task. "
            "One sentence. One responsibility. No 'and'."
        ),
    )
    scope: list[str] = Field(
        ...,
        description="Specific things this task actively does.",
    )
    out_of_scope: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Specific things this task must NOT do. "
            "At least one item required to bound the task clearly."
        ),
    )
    expected_deliverable: str = Field(
        ...,
        description="Description of what the output file contains.",
    )
    output_file: OutputFile = Field(
        ...,
        description="The single file artifact this task produces.",
    )
    dependencies: list[TaskDependency] = Field(
        default_factory=list,
        description=(
            "Task ID and artifacts of other tasks this task depends on. "
            "A dependency exists only when this task cannot execute correctly "
            "without the artifact produced by the other task. "
            "Empty list if no dependencies."
        ),
    )


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

    @model_validator(mode="after")
    def validate_dag_keys_match_ids(self) -> "PlannerOutput":
        for key, task in self.dag.items():
            if key != task.task_id:
                raise ValueError(
                    f"DAG key '{key}' does not match task_id '{task.task_id}'."
                )
        return self

    @model_validator(mode="after")
    def validate_shared_output_paths(self) -> "PlannerOutput":
        _validate_shared_output_paths(self.dag)
        return self

    @model_validator(mode="after")
    def validate_dependencies_exist(self) -> "PlannerOutput":
        task_ids = set(self.dag.keys())
        for task in self.dag.values():
            for dep in task.dependencies:
                if dep.task_id not in task_ids:
                    raise ValueError(
                        f"Task '{task.task_id}' depends on '{dep}' "
                        f"which is not present in the final DAG."
                    )
        return self

    @model_validator(mode="after")
    def validate_no_circular_dependencies(self) -> "PlannerOutput":
        cycle = _detect_cycle(self.dag)
        if cycle :
            raise ValueError(
                "Circular dependency detected in final DAG from task.\n"
                f"{cycle}"
            )
        return self


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 — DAG Verification Agent
# ══════════════════════════════════════════════════════════════════════════


class MissingDependency(BaseModel):
    depends_on_task_id: str = Field(
        ...,
        description=(
            "Task ID whose output is needed. "
            "If the task doesn't exist yet, prefix with 'MISSING: '."
        ),
    )
    reason: str = Field(
        ...,
        description="What artifact is needed and why this task cannot produce it independently.",
    )


class UnnecessaryDependency(BaseModel):
    task_id: str = Field(
        ...,
        description="Dependency task ID that should be removed." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    reason: str = Field(..., description="Why this task's output is not actually consumed.")


class MissingTask(BaseModel):
    suggested_name: str = Field(..., description="Descriptive name for the missing task.")
    reason: str = Field(..., description="Why this task is required for correct execution.")
    would_unblock: str = Field(
        ...,
        description="Which task(s) are currently blocked or incorrectly assuming this task exists.",
    )


class OverlappingTask(BaseModel):
    task_id: str = Field(
        ...,
        description="The overlapping task's ID." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    overlap_description: str = Field(
        ...,
        description="Specific description of the responsibility overlap.",
    )

class VerificationOutput(BaseModel):
    """One instance produced per task being reviewed."""

    task_id: str = Field(
        ...,
        description="The assigned task ID." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    dag_valid_for_task: bool = Field(
        ...,
        description=(
            "False if any missing_dependencies, missing_tasks, or overlapping_tasks exist. "
            "True only if the DAG fully supports this task's execution."
        ),
    )
    summary: str = Field(..., description="1–2 sentences on DAG validity for this task.")
    missing_dependencies: list[MissingDependency] = Field(default_factory=list)
    unnecessary_dependencies: list[UnnecessaryDependency] = Field(default_factory=list)
    missing_tasks: list[MissingTask] = Field(default_factory=list)
    overlapping_tasks: list[OverlappingTask] = Field(default_factory=list)
    scope_corrections: list[str] = Field(
        default_factory=list,
        description="Specific scope changes suggested.",
    )
    output_file_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns about this task's output_file path, mode, or format.",
    )
    suggested_dag_changes: list[str] = Field(
        default_factory=list,
        description="Structural changes not captured by the specific fields above.",
    )

    @model_validator(mode="after")
    def validate_dag_valid_flag(self) -> "VerificationOutput":
        has_issues = bool(
            self.missing_dependencies
            or self.missing_tasks
            or self.overlapping_tasks
        )
        if has_issues and self.dag_valid_for_task:
            raise ValueError(
                "dag_valid_for_task must be False when missing_dependencies, "
                "missing_tasks, or overlapping_tasks are non-empty."
            )
        return self


# ══════════════════════════════════════════════════════════════════════════
# Phase 3 — Validation Agent
# ══════════════════════════════════════════════════════════════════════════


class AcceptedChange(BaseModel):
    change: str = Field(..., description="Description of what was changed.")
    source_task_id: str = Field(
        ...,
        description="Task ID of the verification report that raised this suggestion.",
    )
    applied_to_tasks: list[str] = Field(
        ...,
        min_length=1,
        description="Task IDs structurally affected by this change.",
    )


class RejectedChange(BaseModel):
    change: str = Field(..., description="Description of the rejected suggestion.")
    source_task_id: str = Field(
        ...,
        description="Task ID of the verification report that raised this suggestion.",
    )
    reason: str = Field(..., description="Specific reason for rejection.")


class OutputFileResolution(BaseModel):
    """
    A path issue identified during validation. This RECORDS the concern —
    it does not resolve it. Validation Agent may never assign a new
    output_file.path to an existing task; that authority belongs solely to
    the Dependency Coordinator, which has the artifact-level visibility to
    make a good renaming call. resolution here describes what the concern
    is and that it's deferred, not a path change.
    """

    task_id: str = Field(
        ...,
        description="Task ID of the task that this resolution belongs to." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    concern: str = Field(..., description="The output_file concern identified.")
    resolution: str = Field(
        ...,
        description=(
            "How the concern is being handled at this phase — e.g. deferred "
            "to the Dependency Coordinator with reasoning — never a new path "
            "assigned directly here."
        ),
    )


class ValidationOutput(BaseModel):
    """Canonical, verified final DAG."""

    project_summary: str
    validation_summary: str
    accepted_changes: list[str] = Field(default_factory=list)
    rejected_changes: list[RejectedChange] = Field(default_factory=list)
    output_file_resolutions: list[OutputFileResolution] = Field(default_factory=list)
    dag: dict[str, Task] = Field(
        ..., description="Canonical DAG after resolving all verification reports"
    )

    @model_validator(mode="after")
    def validate_dag_keys_match_ids(self) -> "ValidationOutput":
        for key, task in self.dag.items():
            if key != task.task_id:
                raise ValueError(
                    f"DAG key '{key}' does not match task_id '{task.task_id}'."
                )
        return self

    @model_validator(mode="after")
    def validate_shared_output_paths(self) -> "ValidationOutput":
        _validate_shared_output_paths(self.dag)
        return self

    @model_validator(mode="after")
    def validate_dependencies_exist(self) -> "ValidationOutput":
        task_ids = set(self.dag.keys())
        for task in self.dag.values():
            for dep in task.dependencies:
                if dep.task_id not in task_ids:
                    raise ValueError(
                        f"Task '{task.task_id}' depends on '{dep}' "
                        f"which is not present in the final DAG."
                    )
        return self

    @model_validator(mode="after")
    def validate_no_circular_dependencies(self) -> "ValidationOutput":
        cycle = _detect_cycle(self.dag)
        if cycle :
            raise ValueError(
                "Circular dependency detected in final DAG from task.\n"
                f"{cycle}"
            )
        return self


# ══════════════════════════════════════════════════════════════════════════
# Phase 4 — Dependency Specification Agent
# ══════════════════════════════════════════════════════════════════════════


class ParameterSpec(BaseModel):
    name: str
    type: str
    description: str
    required: bool


class ConsumedFormalDefinition(BaseModel):
    """Implementation-ready artifact definition used by consumers."""

    file_location: str = Field(
        ...,
        description="Exact file path. Must be a file with extension, not a directory.",
    )
    import_statement: str | None = Field(
        default=None,
        description=(
            "Exact import statement the consuming task will use. "
            "Null only if the parent DependencySpec.artifact_type is "
            "api_route accessed over HTTP rather than imported,"
            "or config where project uses config.yml, requirements.txt, etc."
        ),
    )

    signature_or_schema: str = Field(
        ...,
        description=(
            "Complete type-annotated definition. "
            "Not a prose description. Not abbreviated. "
            "E.g.: 'class User(BaseModel):\\n    id: UUID\\n    email: str'"
        ),
    )
    attributes_or_parameters: list[ParameterSpec] = Field(
        ...,
        description="All fields or parameters. Never empty for classes or functions with parameters.",
    )
    return_type: str | None = Field(
        default=None,
        description="Return type for functions. Null for classes and constants.",
    )
    description: str = Field(
        ...,
        description="What this artifact does or contains.",
    )

    @model_validator(mode="after")
    def path_must_be_file(self) -> "ConsumedFormalDefinition":
        if self.file_location.endswith("/"):
            raise ValueError(
                f"file_location must be a file path, not a directory. "
                f"Got: '{self.file_location}'"
            )
        return self

class ProducesFormalDefinition(BaseModel):
    """Definition used in produces_specifications — includes export_statement."""

    file_location: str = Field(
        ...,
        description="Must match the producing task's output_file.path.",
    )
    export_statement: str = Field(
        ...,
        description=(
            "The definition header as it will appear in the output file. "
            "E.g.: 'class UserRepository:' or 'def create_user(data: UserCreate) -> User:'"
        ),
    )
    signature_or_schema: str = Field(
        ...,
        description="Complete type-annotated definition.",
    )
    attributes_or_parameters: list[ParameterSpec] = Field(
        ...,
        description="All fields or parameters.",
    )
    return_type: str | None = Field(default=None)
    description: str


class DependencySpec(BaseModel):
    """
    Spec for one artifact this task consumes from a dependency task.

    Corresponds to exactly one description string inside one TaskDependency
    object on the assigned task's `dependencies` field — not to the whole
    TaskDependency object. A single depends_on_task_id may therefore have
    multiple DependencySpec entries, one per named artifact.
    """

    depends_on_task_id: str = Field(
        ...,
        description="Task ID that produces this artifact. Must exist in the DAG." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc.",
    )
    source_description: str = Field(
        ...,
        description=(
            "The exact string this spec formalizes, copied verbatim from "
            "the matching TaskDependency object's inner dependencies list "
            "on the assigned task. Empty string only when that inner list "
            "was empty and this artifact was inferred instead."
        ),
    )
    dependency_name: str = Field(
        ...,
        description="Exact class/function/constant/route name.",
    )
    purpose: str = Field(
        ...,
        description="Why this task requires this artifact.",
    )
    artifact_type: ArtifactType
    formal_definition: ConsumedFormalDefinition
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    example: str = Field(
        ...,
        description=(
            "Complete usage example as valid code — not prose. "
            "Shows exactly how this task uses the artifact."
        ),
    )
    

    @model_validator(mode="after")
    def import_statement_null_only_for_api_route_or_config(self) -> "DependencySpec":
        if (
            self.formal_definition.import_statement is None
            and self.artifact_type not in ("api_route", "config")
        ):
            raise ValueError(
                "formal_definition.import_statement may only be null when "
                f"artifact_type is 'api_route' or 'config'. Got artifact_type="
                f"'{self.artifact_type}' with a null import_statement."
            )
        return self


class ProducesSpec(BaseModel):
    """Spec for one artifact this task produces for other tasks."""

    artifact_name: str = Field(
        ...,
        description="Exact name as it will appear in the output file.",
    )
    purpose: str = Field(
        ...,
        description="Why this artifact exists and which tasks consume it.",
    )
    artifact_type: ArtifactType
    formal_definition: ProducesFormalDefinition
    constraints: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)


class DependencySpecOutput(BaseModel):
    """One instance per task."""

    task_id: str = Field(
        ...,
        description="Your task id. Write nothing here other than your own task id, character by character." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    dependency_specifications: list[DependencySpec] = Field(
        default_factory=list,
        description=(
            "One entry per description string across all TaskDependency "
            "objects in the assigned task's dependencies field. "
            "Empty if the task has no dependencies."
        ),
    )
    produces_specifications: list[ProducesSpec] = Field(
        default_factory=list,
        description=(
            "Every artifact this task produces that other tasks consume "
            "or that evaluators need to verify. Derived by scanning the "
            "full DAG for tasks that declare a TaskDependency on this task_id."
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 5 — Dependency Coordinator Agent
# ══════════════════════════════════════════════════════════════════════════


class DependencyConflictResolution(BaseModel):
    artifact_name: str
    conflicting_tasks: list[str] = Field(..., min_length=2)
    conflict_type: str = Field(
        default="naming",
        description=(
            "'naming', 'signature', 'type_annotation', 'artifact_type', "
            "'path_collision', or 'missing_producer_definition' — the last "
            "is required for orphaned expectations."
        ),
    )
    conflict_description: str = Field(
        ...,
        description="Specific definition differences — names, types, signatures.",
    )
    resolution: str = Field(
        ...,
        description="Which definition was chosen, what changed, and which rule number applied.",
    )


class CanonicalDefinition(BaseModel):
    """
    The single authoritative definition of an artifact.
    Includes neutral (language-agnostic) and per-format representations.
    Executor Agents use representations[their_format] — never neutral directly.
    """

    file_location: str = Field(
        ...,
        description="Canonical file path. Matches the producer task's finalized output_file.path.",
    )
    import_statement: str | None = Field(
        default=None,
        description=(
            "Canonical import for same-language consumers. "
            "Null for cross-language artifacts."
        ),
    )
    neutral: str = Field(
        ...,
        description=(
            "Language-agnostic definition. Required for every artifact. "
            "JSON Schema for data shapes, OpenAPI 3 fragment for API routes, "
            "pseudocode for function behavior."
        ),
    )
    representations: dict[str, str] = Field(
        ...,
        description=(
            "Map of output_file.format → complete language-specific definition. "
            "At least one entry required. "
            "E.g.: {'python': 'class User(BaseModel): ...', 'typescript': 'interface User {'}"
        ),
    )
    signature_or_schema: str = Field(
        ...,
        description="Final canonical type-annotated definition.",
    )
    attributes_or_parameters: list[ParameterSpec] = Field(
        ...,
        description="Never empty for models, schemas, or functions with parameters.",
    )
    return_type: str | None = Field(default=None)

    @model_validator(mode="after")
    def representations_non_empty(self) -> "CanonicalDefinition":
        if not self.representations:
            raise ValueError("representations must contain at least one format entry.")
        return self


class DependencyContract(BaseModel):
    """One canonical artifact definition covering all producers and consumers."""

    dependency_id: str = Field(
        ...,
        description="Sequential identifier. Format: 'D-001'.",
        pattern=r"^D-\d{3,}$",
    )
    dependency_name: str = Field(..., description="Canonical artifact name.")
    producer_tasks: list[str] = Field(..., min_length=1)
    consumer_tasks: list[str] = Field(default_factory=list)
    artifact_type: ArtifactType
    canonical_definition: CanonicalDefinition
    constraints: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    examples: list[str] = Field(
        default_factory=list,
        description="One usage example per consumer format.",
    )


class CoordinatorOutput(BaseModel):
    """Single source of truth consumed by all Executor agents."""

    integration_summary: str = Field(
        ...,
        description=(
            "2–3 sentences. Artifact count, conflict count, "
            "cross-language boundaries handled, path changes made."
        ),
    )
    resolved_conflicts: list[DependencyConflictResolution] = Field(
        default_factory=list,
        description="Every conflict resolved. Empty only if no conflicts existed.",
    )
    dependency_contracts: list[DependencyContract] = Field(
        ...,
        min_length=1,
        description="One entry per canonical artifact. No artifact in two contracts.",
    )
    dag: dict[str, Task] = Field(..., description="Finalized DAG with canonicalized output_file.path")

    @model_validator(mode="after")
    def validate_dag_keys_match_ids(self) -> "CoordinatorOutput":
        for key, task in self.dag.items():
            if key != task.task_id:
                raise ValueError(
                    f"DAG key '{key}' does not match task_id '{task.task_id}'."
                )
        return self

    @model_validator(mode="after")
    def validate_shared_output_paths(self) -> "CoordinatorOutput":
        _validate_shared_output_paths(self.dag)
        return self

    @model_validator(mode="after")
    def validate_dependencies_exist(self) -> "CoordinatorOutput":
        task_ids = set(self.dag.keys())
        for task in self.dag.values():
            for dep in task.dependencies:
                if dep.task_id not in task_ids:
                    raise ValueError(
                        f"Task '{task.task_id}' depends on '{dep}' "
                        f"which is not present in the final DAG."
                    )
        return self

    @model_validator(mode="after")
    def validate_no_circular_dependencies(self) -> "CoordinatorOutput":
        cycle = _detect_cycle(self.dag)
        if cycle :
            raise ValueError(
                "Circular dependency detected in final DAG from task.\n"
                f"{cycle}"
            )
        return self

    @model_validator(mode="after")
    def validate_unique_dependency_ids(self) -> "CoordinatorOutput":
        ids = [c.dependency_id for c in self.dependency_contracts]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate dependency_ids in dependency_contracts.")
        return self


# ══════════════════════════════════════════════════════════════════════════
# Phase 6 — Executor Agent
# ══════════════════════════════════════════════════════════════════════════

class ContractComplianceEntry(BaseModel):
    """Compliance status for one dependency_id where this task is a producer or consumer."""

    dependency_id: str = Field(
        ...,
        description="D-00N from the dependency contract.",
        pattern=r"^D-\d{3,}$",
    )
    status: ContractStatus
    notes: str = Field(
        ...,
        description=(
            "How the contract was followed (COMPLIANT), "
            "or exactly what was violated (NON_COMPLIANT)."
        ),
    )


class SelfVerification(BaseModel):
    """Executor's honest self-assessment of its own output."""

    objective_completed: bool
    scope_respected: bool
    deliverable_produced: bool
    contract_followed: bool
    output_file_correct: bool


class ExecutorOutput(BaseModel):
    """
    Output of one Executor Agent.
    Contains the complete implementation for one task in a single file.
    """

    task_id: str = Field(
        ...,
        description = "The task ID of the task that this implementation output belongs to." \
        "ID must be a valid task ID." \
        "ID must exist in the DAG." \
        "Format: 'T-001', 'T-002', etc."
    )
    task_summary: str = Field(
        ...,
        description=(
            "What was implemented and how the objective was satisfied. "
            "Names the contract artifacts produced."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Every assumption made where the contract or task was ambiguous. "
            "Empty if no assumptions were needed."
        ),
    )
    implementation: str = Field(
        ...,
        description=(
            "Complete file content ready to write verbatim to task.output_file.path. "
            "If task.output_file.mode is 'a', this is ONLY the new content to append — "
            "it must not repeat content already present in the file being appended to. "
            "Not a summary. Not pseudocode. The actual implementation."
        ),
    )
    contract_compliance: list[ContractComplianceEntry] = Field(
        ...,
        description=(
            "One entry per dependency_id where this task is listed as a producer "
            "or consumer in the dependency contract. No entry for dependency_ids "
            "unrelated to this task."
        ),
    )
    self_verification: SelfVerification

    @model_validator(mode="after")
    def implementation_non_empty(self) -> "ExecutorOutput":
        if not self.implementation or not self.implementation.strip():
            raise ValueError(
                "implementation must be non-empty complete file content."
            )
        return self

    @model_validator(mode="after")
    def non_compliant_contracts_flagged(self) -> "ExecutorOutput":
        """If self_verification.contract_followed is False,
        at least one NON_COMPLIANT entry must exist."""
        if not self.self_verification.contract_followed:
            has_violation = any(
                e.status == "NON_COMPLIANT" for e in self.contract_compliance
            )
            if not has_violation:
                raise ValueError(
                    "self_verification.contract_followed is False but no "
                    "NON_COMPLIANT entry exists in contract_compliance."
                )
        return self


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