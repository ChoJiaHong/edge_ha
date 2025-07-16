from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class ServiceSpec:
    serviceType: str
    frequencyLimit: List[int]
    workAbility: Dict[str, int]
    gpuMemoryRequest: int

    @staticmethod
    def from_dict(data: Dict) -> 'ServiceSpec':
        return ServiceSpec(
            serviceType=data['serviceType'],
            frequencyLimit=data.get('frequencyLimit', []),
            workAbility=data.get('workAbility', {}),
            gpuMemoryRequest=data.get('gpuMemoryRequest', 0)
        )

@dataclass
class ServiceInstance:
    podIP: str
    hostPort: int
    serviceType: str
    currentConnection: int
    nodeName: str
    hostIP: str
    frequencyLimit: List[int]
    currentFrequency: int
    workloadLimit: float

    @staticmethod
    def from_dict(data: Dict) -> 'ServiceInstance':
        return ServiceInstance(
            podIP=data['podIP'],
            hostPort=data['hostPort'],
            serviceType=data['serviceType'],
            currentConnection=data.get('currentConnection', 0),
            nodeName=data['nodeName'],
            hostIP=data.get('hostIP', ''),
            frequencyLimit=data.get('frequencyLimit', []),
            currentFrequency=data.get('currentFrequency', 0),
            workloadLimit=data.get('workloadLimit', 0.0)
        )

    def to_dict(self) -> Dict:
        return {
            'podIP': self.podIP,
            'hostPort': self.hostPort,
            'serviceType': self.serviceType,
            'currentConnection': self.currentConnection,
            'nodeName': self.nodeName,
            'hostIP': self.hostIP,
            'frequencyLimit': self.frequencyLimit,
            'currentFrequency': self.currentFrequency,
            'workloadLimit': self.workloadLimit,
        }

@dataclass
class Subscription:
    agentIP: str
    agentPort: int
    podIP: str
    serviceType: str
    nodeName: str

    @staticmethod
    def from_dict(data: Dict) -> 'Subscription':
        return Subscription(
            agentIP=data['agentIP'],
            agentPort=data['agentPort'],
            podIP=data['podIP'],
            serviceType=data['serviceType'],
            nodeName=data.get('nodeName', '')
        )

    def to_dict(self) -> Dict:
        return {
            'agentIP': self.agentIP,
            'agentPort': self.agentPort,
            'podIP': self.podIP,
            'serviceType': self.serviceType,
            'nodeName': self.nodeName
        }

@dataclass
class NodeStatus:
    nodeName: str
    status: str

    @staticmethod
    def from_dict(item: Dict) -> 'NodeStatus':
        # expecting {'name': name, 'status': status}
        return NodeStatus(nodeName=item['name'], status=item['status'])

