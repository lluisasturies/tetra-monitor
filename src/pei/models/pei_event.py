from dataclasses import dataclass

@dataclass
class PEIEvent:
    type: str
    grupo: int = 0
    ssi: int = 0
