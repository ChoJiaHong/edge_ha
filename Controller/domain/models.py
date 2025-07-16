from dataclasses import dataclass, asdict
from typing import List, Dict

@dataclass
class ServiceInstance:
    podIP: str
    hostPort: int
    serviceType: str
    currentConnection: int
    nodeName: str
    hostIP: str
    frequencyLimit: List[int]
    currentFrequency: float
    workloadLimit: float
    originalIndex: int = 0

    def to_dict(self) -> Dict:
        d = asdict(self)
        d.pop('originalIndex', None)
        return d
