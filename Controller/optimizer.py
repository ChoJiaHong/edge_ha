"""Service optimization algorithms.

This module keeps the original public functions but internally delegates
implementation to the application layer defined in
``Controller.application.optimizer_service``. This helps keep compatibility
while following a Domain Driven Design approach.
"""

from typing import List, Tuple
from dataclasses import asdict

from Controller.domain.models import ServiceInstance
from Controller.application.optimizer_service import optimize as _optimize


def _convert_to_instances(service_list: List[dict]) -> List[ServiceInstance]:
    return [ServiceInstance(**svc) for svc in service_list]


def _convert_to_dicts(instances: List[ServiceInstance]) -> List[dict]:
    return [inst.to_dict() for inst in instances]


def optimize(servicetype: str, agentcount: int, servicelist: List[dict]) -> Tuple[str, List[dict]]:
    """Optimize agent allocation.

    Parameters are kept for backward compatibility.
    """
    status, updated = _optimize(servicetype, agentcount, _convert_to_instances(servicelist))
    return status, _convert_to_dicts(updated)


# simple strategies ---------------------------------------------------------

def uniform(servicetype: str, agentcount: int, servicelist: List[dict]) -> Tuple[str, List[dict]]:
    """Distribute agents evenly across instances."""
    instances = _convert_to_instances(servicelist)
    updated = []
    for inst in instances:
        if inst.serviceType == servicetype:
            inst = ServiceInstance(
                **{**inst.to_dict(),
                   "currentConnection": 0,
                   "currentFrequency": inst.frequencyLimit[0]},
                originalIndex=inst.originalIndex,
            )
        updated.append(inst)

    allocated = 0
    while allocated < agentcount:
        for i, inst in enumerate(updated):
            if allocated == agentcount:
                break
            if inst.serviceType == servicetype:
                updated[i] = ServiceInstance(
                    **{**inst.to_dict(),
                       "currentConnection": inst.currentConnection + 1},
                    originalIndex=inst.originalIndex,
                )
                allocated += 1
    return "success", _convert_to_dicts(updated)


def most_remaining(servicetype: str, agentcount: int, servicelist: List[dict]) -> Tuple[str, List[dict]]:
    """Assign agents to instances with the most remaining capacity first."""
    instances = [ServiceInstance(**s, originalIndex=i) for i, s in enumerate(servicelist)]
    def remaining(inst: ServiceInstance) -> float:
        return inst.workloadLimit - inst.currentConnection * inst.frequencyLimit[0]
    instances.sort(key=remaining, reverse=True)
    allocated = 0
    while allocated < agentcount:
        for i, inst in enumerate(instances):
            if allocated == agentcount:
                break
            if inst.serviceType == servicetype:
                new_conn = inst.currentConnection + 1
                instances[i] = ServiceInstance(
                    **{**inst.to_dict(),
                       "currentConnection": new_conn,
                       "currentFrequency": inst.frequencyLimit[0]},
                    originalIndex=inst.originalIndex,
                )
                allocated += 1
                instances.sort(key=remaining, reverse=True)
                break
        else:
            break
    return "success", _convert_to_dicts(instances)
