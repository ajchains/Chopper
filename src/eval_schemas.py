"""
Pydantic models for the Evaluator Agent's output (Phase 7). Companion to the
pipeline's shared "Output Models" module — same conventions, same primitive
style, just scoped to evaluation. Consumes, by reference only, the Task
(Phase 1), DependencyContract (Phase 5), and ExecutorOutput (Phase 6) models
defined elsewhere in this package; this file does not redefine them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TestCategory = Literal["isolation", "behavioral", "integration"]

TestType = Literal[
    "schema",
    "value",
    "contract_ref",
    "behavior",
    "integration",
]

Severity = Literal["critical", "major", "minor"]

TestOutcome = Literal["PASS", "FAIL", "SKIP"]

EvalMode = Literal["llm_judge", "execution"]

FaultLocus = Literal["executor", "contract", "both"]

Verdict = Literal["PASS", "EXECUTOR_FAULT", "CONTRACT_INCOMPLETE"]

VerdictConfidence = Literal["high", "medium", "low"]

# Which test_type values are legal under each category. Used to keep the two
# fields from drifting apart on a TestCase (e.g. category="integration" with
# test_type="value" would silently misfile a test).
_CATEGORY_TEST_TYPES: dict[str, set[str]] = {
    "isolation": {"schema", "value", "contract_ref"},
    "behavioral": {"behavior"},
    "integration": {"integration"},
}


# ══════════════════════════════════════════════════════════════════════════
# Shared Evaluator Primitives
# ══════════════════════════════════════════════════════════════════════════


class TestCase(BaseModel):
    """
    A single testable claim derived from a dependency contract clause.
    Isolation and behavioral test cases evaluate one task's output against
    its own contract obligations. Integration test cases evaluate whether
    this task's output and a peer task's output are mutually compatible.
    """

    test_id: str = Field(
        ...,
        description=(
            "Sequential identifier. Format: 'TC-001', 'TC-002', etc. "
            "Zero-padded three-digit suffix."
        ),
    )
    task_id: str = Field(
        ..., description="ID of the task whose output this test case evaluates."
    )
    peer_task_id: str | None = Field(
        default=None,
        description=(
            "ID of the peer task on the other side of the interface boundary. "
            "Required when test_type is 'integration'. Must be omitted otherwise."
        ),
    )
    category: TestCategory = Field(
        ...,
        description=(
            "'isolation' — does this task's output satisfy its own contract obligations. "
            "'behavioral' — does the artifact behave correctly when invoked. "
            "'integration' — do this task's outputs and the peer's outputs actually fit together."
        ),
    )
    test_type: TestType = Field(
        ...,
        description=(
            "'schema' — output file exists, parses correctly, has required fields and types. "
            "'value' — a specific field equals, contains, or matches a contract-specified value. "
            "'contract_ref' — an exact name, signature, or schema appears verbatim as specified. "
            "'behavior' — call the artifact and observe the return value or side effect. "
            "'integration' — the name, signature, or schema this task references matches what "
            "the peer task literally produced."
        ),
    )
    dependency_ref: str = Field(
        ...,
        description=(
            "Identifier of the DependencyContract (or the specific produces_specification / "
            "dependency_specification within it) this test case verifies."
        ),
    )
    description: str = Field(
        ..., description="What this test case verifies, in one or two sentences."
    )
    expected_verbatim: str | None = Field(
        default=None,
        description=(
            "The exact name, signature, or schema text the contract specifies. "
            "Required when test_type is 'contract_ref'."
        ),
    )
    assertion: str = Field(
        ...,
        description=(
            "For 'schema' / 'value' / 'contract_ref': typed pseudocode you can evaluate by "
            "reading the implementation text. No vague prose. "
            "For 'behavior' / 'integration': a one-line summary of what executable_stub tests."
        ),
    )
    sandbox_required: bool = Field(
        ...,
        description="Always true for 'behavior' and 'integration'. Always false otherwise.",
    )
    executable_stub: str | None = Field(
        default=None,
        description=(
            "Complete, runnable test function — correct imports using the actual file paths "
            "from the executor outputs, arrange, act, assert. Required when test_type is "
            "'behavior' or 'integration'. Write it as if it runs unchanged tomorrow."
        ),
    )
    severity: Severity = Field(
        ...,
        description=(
            "'critical' — the contract's core obligation or the integration boundary cannot "
            "work without this. 'major' — significant deviation that would cause downstream "
            "failures. 'minor' — convention or style issue."
        ),
    )

    @model_validator(mode="after")
    def category_must_match_test_type(self) -> "TestCase":
        allowed = _CATEGORY_TEST_TYPES[self.category]
        if self.test_type not in allowed:
            raise ValueError(
                f"Test '{self.test_id}' has category '{self.category}' but test_type "
                f"'{self.test_type}', which is not one of {sorted(allowed)}."
            )
        return self

    @model_validator(mode="after")
    def integration_tests_require_peer(self) -> "TestCase":
        if self.test_type == "integration" and not self.peer_task_id:
            raise ValueError(
                f"Test '{self.test_id}' is an integration test and must set peer_task_id."
            )
        if self.test_type != "integration" and self.peer_task_id:
            raise ValueError(
                f"Test '{self.test_id}' has test_type '{self.test_type}' but sets "
                f"peer_task_id; only integration tests reference a peer."
            )
        return self

    @model_validator(mode="after")
    def sandbox_and_stub_required_for_execution_tests(self) -> "TestCase":
        needs_execution = self.test_type in ("behavior", "integration")
        if needs_execution:
            if not self.sandbox_required:
                raise ValueError(
                    f"Test '{self.test_id}' has test_type '{self.test_type}' and must set "
                    f"sandbox_required=True."
                )
            if not self.executable_stub or not self.executable_stub.strip():
                raise ValueError(
                    f"Test '{self.test_id}' has test_type '{self.test_type}' and must include "
                    f"a complete executable_stub."
                )
        elif self.sandbox_required:
            raise ValueError(
                f"Test '{self.test_id}' has test_type '{self.test_type}', which is evaluated "
                f"by reading implementation text; sandbox_required must be False."
            )
        return self

    @model_validator(mode="after")
    def contract_ref_requires_expected_verbatim(self) -> "TestCase":
        if self.test_type == "contract_ref" and not (
            self.expected_verbatim and self.expected_verbatim.strip()
        ):
            raise ValueError(
                f"Test '{self.test_id}' has test_type 'contract_ref' and must set "
                f"expected_verbatim to the exact contract text being checked."
            )
        return self


class TestResult(BaseModel):
    """The evaluator's verdict on a single TestCase, produced in Step 3."""

    test_id: str = Field(..., description="Must match the test_id of the TestCase evaluated.")
    outcome: TestOutcome
    eval_mode: EvalMode = Field(
        ...,
        description=(
            "'llm_judge' — evaluated by reading implementation text. This covers static "
            "tests, integration tests statically resolved via the peer's actual code, and "
            "every current SKIP (sandbox not available in this phase). "
            "'execution' — reserved for once executable_stub has actually been run in a "
            "sandbox; not produced by this phase."
        ),
    )
    notes: str = Field(
        ...,
        description=(
            "Evidence for the outcome. For FAIL, quote the exact contract clause that was "
            "violated. For SKIP, state why — e.g. 'sandbox not available — executable_stub "
            "ready for Phase 2', or the linked gap."
        ),
    )
    fault_locus: FaultLocus | None = Field(
        default=None,
        description=(
            "Required when outcome is 'FAIL'. 'executor' — clause is clear, executor did not "
            "follow it. 'contract' — clause is ambiguous, executor's interpretation is "
            "reasonable, contract is the problem. 'both' — clause is partially specified and "
            "the executor made a poor choice, but a clearer contract would have prevented it. "
            "Must be omitted for PASS and SKIP."
        ),
    )
    gap_id: str | None = Field(
        default=None,
        description=(
            "Set only when outcome is 'SKIP' because the underlying TestCase is gap-linked. "
            "Must reference a real ContractCoverageGap.gap_id."
        ),
    )

    @model_validator(mode="after")
    def notes_required(self) -> "TestResult":
        if not self.notes or not self.notes.strip():
            raise ValueError(f"Test result '{self.test_id}' must include notes.")
        return self

    @model_validator(mode="after")
    def fault_locus_only_on_fail(self) -> "TestResult":
        if self.outcome == "FAIL" and self.fault_locus is None:
            raise ValueError(f"Test result '{self.test_id}' is FAIL and must set fault_locus.")
        if self.outcome != "FAIL" and self.fault_locus is not None:
            raise ValueError(
                f"Test result '{self.test_id}' has outcome '{self.outcome}'; fault_locus is "
                f"only set for FAIL."
            )
        return self

    @model_validator(mode="after")
    def gap_id_only_on_skip(self) -> "TestResult":
        if self.gap_id is not None and self.outcome != "SKIP":
            raise ValueError(
                f"Test result '{self.test_id}' sets gap_id but outcome is '{self.outcome}'; "
                f"gap_id is only set for gap-linked SKIPs."
            )
        return self


class ContractCoverageGap(BaseModel):
    """
    A contract clause too ambiguous to write a meaningful assertion against.
    Recorded while generating test cases in Step 2 — never invented after
    the fact to explain away a FAIL.
    """

    gap_id: str = Field(
        ..., description="Sequential identifier. Format: 'GAP-001', 'GAP-002', etc."
    )
    dependency_ref: str = Field(
        ..., description="Identifier of the DependencyContract containing the ambiguous clause."
    )
    quoted_clause: str = Field(
        ..., description="The ambiguous contract clause, quoted verbatim — not paraphrased."
    )
    ambiguity: str = Field(..., description="What specifically is ambiguous about the clause.")
    impact: str = Field(
        ..., description="What cannot be verified, or what could go wrong, as a result."
    )
    suggested_addition: str = Field(
        ..., description="Proposed contract text that would resolve the ambiguity."
    )


class ExecutorRetryHint(BaseModel):
    """Tells one executor exactly what to produce instead. Populated only on EXECUTOR_FAULT."""

    task_id: str = Field(..., description="ID of the task whose executor must retry.")
    quoted_clause: str = Field(
        ...,
        description="The specific contract clause the executor did not satisfy, quoted verbatim.",
    )
    required_change: str = Field(
        ..., description="Exactly what the executor must produce instead."
    )
    related_test_ids: list[str] = Field(
        default_factory=list,
        description="TestCase IDs whose FAIL results motivated this hint.",
    )


class ContractPatch(BaseModel):
    """Instructs which contracts must be amended and who must re-run. Populated only on CONTRACT_INCOMPLETE."""

    target_dependency_ids: list[str] = Field(
        ..., min_length=1, description="DependencyContract identifiers that need amendment."
    )
    gap_ids: list[str] = Field(
        ..., min_length=1, description="ContractCoverageGap IDs this patch resolves."
    )
    patch_summary: str = Field(..., description="What must change in the contract(s), and why.")
    tasks_to_rerun: list[str] = Field(
        ..., min_length=1, description="Task IDs that must re-run once the contract is patched."
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 7 — Evaluator Agent
# ══════════════════════════════════════════════════════════════════════════


class EvaluatorOutput(BaseModel):
    """Output of an Evaluator Agent (Phase 7). Verdict on one task's Executor output."""

    task_id: str = Field(..., description="ID of the task being evaluated.")
    verdict: Verdict
    verdict_confidence: VerdictConfidence = Field(
        ...,
        description=(
            "'high' — all critical tests ran and resolved, no critical SKIPs. "
            "'medium' — some critical or major tests were skipped (sandbox pending or gaps). "
            "'low' — majority of critical tests skipped; sandbox execution needed before this "
            "verdict can be trusted."
        ),
    )
    verdict_reasoning: str = Field(
        ...,
        description="Explanation for the verdict. Quote contract clauses directly, do not paraphrase.",
    )
    test_cases: list[TestCase] = Field(..., min_length=1)
    test_results: dict[str, TestResult] = Field(
        ..., description="Keyed by test_id (e.g. 'TC-001')."
    )
    coverage_gaps: list[ContractCoverageGap] = Field(default_factory=list)
    contract_patch: ContractPatch | None = Field(
        default=None, description="Populated only when verdict is 'CONTRACT_INCOMPLETE'."
    )
    executor_retry_hints: list[ExecutorRetryHint] = Field(
        default_factory=list, description="Populated only when verdict is 'EXECUTOR_FAULT'."
    )

    @model_validator(mode="after")
    def validate_result_keys_match_ids(self) -> "EvaluatorOutput":
        for key, result in self.test_results.items():
            if key != result.test_id:
                raise ValueError(
                    f"test_results key '{key}' does not match TestResult.test_id '{result.test_id}'."
                )
        return self

    @model_validator(mode="after")
    def validate_test_case_ids_unique(self) -> "EvaluatorOutput":
        seen: set[str] = set()
        for tc in self.test_cases:
            if tc.test_id in seen:
                raise ValueError(f"Duplicate test_id '{tc.test_id}' in test_cases.")
            seen.add(tc.test_id)
        return self

    @model_validator(mode="after")
    def validate_gap_ids_unique(self) -> "EvaluatorOutput":
        seen: set[str] = set()
        for gap in self.coverage_gaps:
            if gap.gap_id in seen:
                raise ValueError(f"Duplicate gap_id '{gap.gap_id}' in coverage_gaps.")
            seen.add(gap.gap_id)
        return self

    @model_validator(mode="after")
    def validate_every_test_case_has_exactly_one_result(self) -> "EvaluatorOutput":
        case_ids = {tc.test_id for tc in self.test_cases}
        result_ids = set(self.test_results.keys())
        missing = case_ids - result_ids
        if missing:
            raise ValueError(f"Test case(s) {sorted(missing)} have no TestResult.")
        orphaned = result_ids - case_ids
        if orphaned:
            raise ValueError(
                f"TestResult(s) {sorted(orphaned)} reference test_id(s) not present in test_cases."
            )
        return self

    @model_validator(mode="after")
    def validate_gap_linked_skips_reference_real_gaps(self) -> "EvaluatorOutput":
        gap_ids = {gap.gap_id for gap in self.coverage_gaps}
        for result in self.test_results.values():
            if result.gap_id is not None and result.gap_id not in gap_ids:
                raise ValueError(
                    f"Test result '{result.test_id}' references gap_id '{result.gap_id}' "
                    f"which is not present in coverage_gaps."
                )
        return self

    @model_validator(mode="after")
    def validate_feedback_payload_matches_verdict(self) -> "EvaluatorOutput":
        if self.verdict == "PASS":
            if self.contract_patch is not None:
                raise ValueError("verdict is 'PASS'; contract_patch must be null.")
            if self.executor_retry_hints:
                raise ValueError("verdict is 'PASS'; executor_retry_hints must be empty.")
        elif self.verdict == "EXECUTOR_FAULT":
            if self.contract_patch is not None:
                raise ValueError("verdict is 'EXECUTOR_FAULT'; contract_patch must be null.")
            if not self.executor_retry_hints:
                raise ValueError(
                    "verdict is 'EXECUTOR_FAULT' and must populate executor_retry_hints."
                )
        elif self.verdict == "CONTRACT_INCOMPLETE":
            if self.executor_retry_hints:
                raise ValueError(
                    "verdict is 'CONTRACT_INCOMPLETE'; executor_retry_hints must be empty."
                )
            if self.contract_patch is None:
                raise ValueError(
                    "verdict is 'CONTRACT_INCOMPLETE' and must populate contract_patch."
                )
        return self

    @model_validator(mode="after")
    def validate_contract_patch_gap_ids_exist(self) -> "EvaluatorOutput":
        if self.contract_patch is None:
            return self
        gap_ids = {gap.gap_id for gap in self.coverage_gaps}
        missing = set(self.contract_patch.gap_ids) - gap_ids
        if missing:
            raise ValueError(
                f"contract_patch references gap_id(s) {sorted(missing)} not present in coverage_gaps."
            )
        return self

    @model_validator(mode="after")
    def validate_retry_hint_related_tests_exist(self) -> "EvaluatorOutput":
        case_ids = {tc.test_id for tc in self.test_cases}
        for hint in self.executor_retry_hints:
            missing = set(hint.related_test_ids) - case_ids
            if missing:
                raise ValueError(
                    f"executor_retry_hint for task '{hint.task_id}' references test_id(s) "
                    f"{sorted(missing)} not present in test_cases."
                )
        return self

    @model_validator(mode="after")
    def validate_pass_has_no_critical_or_major_fail(self) -> "EvaluatorOutput":
        if self.verdict != "PASS":
            return self
        severity_by_id = {tc.test_id: tc.severity for tc in self.test_cases}
        for result in self.test_results.values():
            if result.outcome == "FAIL" and severity_by_id.get(result.test_id) in (
                "critical",
                "major",
            ):
                raise ValueError(
                    f"verdict is 'PASS' but test '{result.test_id}' is a critical/major FAIL."
                )
        return self

    @model_validator(mode="after")
    def validate_executor_fault_has_qualifying_fail(self) -> "EvaluatorOutput":
        if self.verdict != "EXECUTOR_FAULT":
            return self
        severity_by_id = {tc.test_id: tc.severity for tc in self.test_cases}
        qualifies = any(
            result.outcome == "FAIL"
            and severity_by_id.get(result.test_id) in ("critical", "major")
            and result.fault_locus in ("executor", "both")
            for result in self.test_results.values()
        )
        if not qualifies:
            raise ValueError(
                "verdict is 'EXECUTOR_FAULT' but no critical/major FAIL has fault_locus "
                "'executor' or 'both'."
            )
        return self

    @model_validator(mode="after")
    def validate_high_confidence_has_no_critical_skips(self) -> "EvaluatorOutput":
        if self.verdict_confidence != "high":
            return self
        severity_by_id = {tc.test_id: tc.severity for tc in self.test_cases}
        for result in self.test_results.values():
            if result.outcome == "SKIP" and severity_by_id.get(result.test_id) == "critical":
                raise ValueError(
                    f"verdict_confidence is 'high' but test '{result.test_id}' is a critical SKIP."
                )
        return self