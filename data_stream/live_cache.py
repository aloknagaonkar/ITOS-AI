from dataclasses import dataclass, field
@dataclass
class LiveCache:
    quotes:dict=field(default_factory=dict)
    depth:dict=field(default_factory=dict)
    greeks:dict=field(default_factory=dict)
