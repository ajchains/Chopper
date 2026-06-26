"""
Registry of (chain_builder, node_fn) per phase.
Uses relative imports to avoid circular self-import from within the package.
"""

from __future__ import annotations

from nodes import coordinator
from nodes import dependency
from nodes import evaluator
from nodes import executor
from nodes import planner
from nodes import validation
from nodes import verification
import nodes.refine_prompt as refine_prompt_mod

from nodes.planner import planner_agent

REGISTRY = {
    "refine_prompt":         (refine_prompt_mod.build_chain,  refine_prompt_mod.refine_prompt),
    "planner":               (planner.build_chain,            planner.planner_agent),
    "dag_verification":      (verification.build_chain,       verification.dag_verification),
    "dag_validation":        (validation.build_chain,         validation.dag_validation),
    "dependency_resolution": (dependency.build_chain,         dependency.dependency_resolution),
    "coordinator":           (coordinator.build_chain,        coordinator.coordinator),
    "executor":              (executor.build_chain,           executor.executor),
    "evaluator":             (evaluator.build_chain,          evaluator.evaluator),
}