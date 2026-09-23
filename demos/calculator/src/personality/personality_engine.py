import random

class PersonalityEngine:
    def __init__(self, chaos_mode: bool = False):
        self.chaos_mode = chaos_mode
        self.responses = [
            "Behold, the answer is",
            "The universe whispers",
            "After much calculation, I present",
            "It is undeniably"
        ]
        self.chaos_responses = [
            "Witness the madness:",
            "The void screams",
            "Chaos dictates",
            "Numbers are lies, but here is"
        ]

    def format_result(self, result: float) -> str:
        if self.chaos_mode:
            prefix = random.choice(self.chaos_responses)
        else:
            prefix = random.choice(self.responses)
        return f"{prefix} {result}"