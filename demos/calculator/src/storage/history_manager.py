import json
import os

class HistoryManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def append(self, entry: str) -> None:
        history = self.get_all()
        history.append(entry)
        with open(self.storage_path, 'w') as f:
            json.dump(history, f)

    def get_all(self) -> list[str]:
        if not os.path.exists(self.storage_path):
            return []
        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []