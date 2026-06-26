from collections import defaultdict, deque
from pydantic import BaseModel
from schemas import Task


def to_markdown(obj, level=2):
    md = []

    if isinstance(obj, BaseModel):
        obj = obj.model_dump()

    if isinstance(obj, dict):
        for key, value in obj.items():
            heading = "#" * level
            title = key.replace("_", " ").title()

            if isinstance(value, (dict, BaseModel, list)):
                md.append(f"{heading} {title}")
                md.append(to_markdown(value, level + 1))
            else:
                md.append(f"{heading} {title}")
                md.append(str(value))
                md.append("")

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, BaseModel)):
                md.append(to_markdown(item, level))
            else:
                md.append(f"- {item}")

    else:
        md.append(str(obj))

    return "\n".join(md)


def topological_order(dag: dict[str, Task]) -> list[str]:
    indegree = {task_id: 0 for task_id in dag}
    graph = defaultdict(list)

    for task in dag.values():
        for dep in task.dependencies:
            parent = dep.task_id

            if parent not in dag:
                raise ValueError(
                    f"Task '{task.task_id}' depends on unknown task '{parent}'"
                )

            graph[parent].append(task.task_id)
            indegree[task.task_id] += 1

    queue = deque(
        sorted(task_id for task_id, degree in indegree.items() if degree == 0)
    )

    order = []

    while queue:
        node = queue.popleft()
        order.append(node)

        for child in sorted(graph[node]):
            indegree[child] -= 1

            if indegree[child] == 0:
                queue.append(child)

    if len(order) != len(dag):
        remaining = [task_id for task_id, degree in indegree.items() if degree > 0]
        raise ValueError(
            f"Cycle detected (or unresolved dependency). Remaining tasks: {remaining}"
        )

    return order


def print_dag(dag: dict[str, Task], own_task: str | None = None) -> str:
    # Build reverse dependency map: task_id -> list of tasks that depend on it
    reverse_deps: dict[str, list[str]] = defaultdict(list)
    for task in dag.values():
        for dep in task.dependencies:
            reverse_deps[dep.task_id].append(task.task_id)

    md = ["# DAG", ""]

    for task_id in topological_order(dag):
        task = dag[task_id]
        you = " (YOU)" if task_id == own_task else ""

        md.append(f"## {task.task_id}{you}")
        md.append(f"**Name:** {task.task_name}")
        md.append("")

        md.append("### Depends On")
        deps = sorted(dep.task_id for dep in task.dependencies)
        if deps:
            md.extend(f"- {d}" for d in deps)
        else:
            md.append("- None")

        md.append("")
        md.append("### Required By")
        children = sorted(reverse_deps[task_id])
        if children:
            md.extend(f"- {child}" for child in children)
        else:
            md.append("- None")

        md.append("")
        md.append("### Task Details")
        md.append(to_markdown(task, level=4))
        md.append("")

    return "\n".join(md)