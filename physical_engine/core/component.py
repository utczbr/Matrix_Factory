from typing import Optional, Dict, Any

class Component:
    def __init__(self):
        self._initialized = False

    def initialize(self, dt: float = 0.0, registry: Optional['ComponentRegistry'] = None) -> None:
        self._initialized = True

    def step(self, t: float) -> None:
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}
