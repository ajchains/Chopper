import math

class MathEngine:
    def __init__(self):
        self._allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}

    def evaluate(self, expression: str) -> float:
        try:
            return float(eval(expression, {"__builtins__": {}}, self._allowed_names))
        except Exception as e:
            raise ValueError(f"Invalid expression: {expression}") from e

    def get_supported_operations(self) -> list[str]:
        return [k for k in self._allowed_names.keys() if callable(self._allowed_names[k])]