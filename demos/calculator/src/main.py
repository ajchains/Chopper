import sys
from src.engine.math_engine import MathEngine
from src.storage.history_manager import HistoryManager
from src.personality.personality_engine import PersonalityEngine
from src.nlp.nlp_processor import NLPProcessor

def run_cli():
    math_engine = MathEngine()
    history = HistoryManager('history.json')
    personality = PersonalityEngine(chaos_mode=False)
    nlp = NLPProcessor(math_engine.get_supported_operations())
    
    print('Calculator initialized. Type "exit" to quit.')
    
    while True:
        try:
            query = input('>> ')
            if query.lower() in ['exit', 'quit']:
                break
            
            if not query.strip():
                continue
                
            expression = nlp.parse(query)
            result = math_engine.evaluate(expression)
            formatted_result = personality.format_result(result)
            
            print(formatted_result)
            history.append(f'{query} = {result}')
            
        except Exception as e:
            print(f'Error: {e}')

if __name__ == '__main__':
    run_cli()