from typing import List
from . import optimizer
from ..domain.models import ServiceInstance, ServiceSpec

# wrapper around existing optimizer function

def compute_frequency(serviceType: str, agentCounter: int, services: List[ServiceInstance]) -> List[ServiceInstance]:
    service_dicts = [s.to_dict() for s in services]
    status, relation_list = optimizer.optimize(serviceType, agentCounter, service_dicts)
    if status == 'fail':
        return []
    return [ServiceInstance.from_dict(d) for d in relation_list]


def deploy_service(serviceType: str, node: str, host_port: int, host_ip: str, spec: ServiceSpec) -> ServiceInstance:
    return ServiceInstance(
        podIP=f'{host_ip}',
        hostPort=host_port,
        serviceType=serviceType,
        currentConnection=0,
        nodeName=node,
        hostIP=host_ip,
        frequencyLimit=spec.frequencyLimit,
        currentFrequency=spec.frequencyLimit[0],
        workloadLimit=spec.workAbility.get(node, 0)
    )


def adjust_frequency(serviceType: str, services: List[ServiceInstance]) -> None:
    for s in services:
        if s.serviceType == serviceType:
            s.currentFrequency = min(s.frequencyLimit)
