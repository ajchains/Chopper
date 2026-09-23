import re
from src.engine.math_engine import MathEngine

class NLPProcessor:
    def __init__(self, supported_ops: list[str]):
        self.supported_ops = supported_ops
        self.mapping = {
            'plus': '+',
            'add': '+',
            'minus': '-',
            'subtract': '-',
            'times': '*',
            'multiply': '*',
            'divided by': '/',
            'divide': '/',
            'square root of': 'sqrt',
            'sqrt': 'sqrt'
        }

    def parse(self, query: str) -> str:
        query_lower = query.lower()
        
        # Handle square root specifically
        if 'sqrt' in query_lower or 'square root' in query_lower:
            match = re.search(r'\d+', query_lower)
            if match:
                return f'sqrt({match.group()})'
        
        # Handle binary operations
        for phrase, op in self.mapping.items():
            if phrase in query_lower:
                parts = re.findall(r'\d+', query_lower)
                if len(parts) >= 2:
                    return f'{parts[0]} {op} {parts[1]}'
        
        return query