from dataclasses import replace
from typing import List, Tuple

from Controller.domain.models import ServiceInstance


def optimize(service_type: str, agent_count: int, instances: List[ServiceInstance]) -> Tuple[str, List[ServiceInstance]]:
    """Allocate agents across service instances.

    Parameters
    ----------
    service_type: str
        Target service type for optimization.
    agent_count: int
        Number of agents requesting the service.
    instances: List[ServiceInstance]
        Current list of service instances.
    Returns
    -------
    status: str
        'success' or 'fail'.
    updated_instances: List[ServiceInstance]
        Instances updated with new connection counts and frequencies.
    """
    status = "success"
    allocated = 0

    # prepare instances
    processed = [replace(inst, originalIndex=i,
                         currentConnection=0 if inst.serviceType == service_type else inst.currentConnection)
                 for i, inst in enumerate(instances)]

    def remain_workload(inst: ServiceInstance) -> float:
        return inst.workloadLimit - inst.currentConnection * inst.frequencyLimit[0]

    def pred_freq(inst: ServiceInstance, extra: int = 1) -> float:
        return inst.workloadLimit / (inst.currentConnection + extra)

    # stage 1: use default frequency
    processed.sort(key=remain_workload, reverse=True)
    idx = 0
    while allocated < agent_count and idx < len(processed):
        inst = processed[idx]
        if inst.serviceType == service_type and remain_workload(inst) >= inst.frequencyLimit[0]:
            new_inst = replace(
                inst,
                currentConnection=inst.currentConnection + 1,
                currentFrequency=inst.frequencyLimit[0]
            )
            processed[idx] = new_inst
            allocated += 1
            processed.sort(key=remain_workload, reverse=True)
            idx = 0
        else:
            idx += 1

    if allocated == 0:
        status = "fail"
        processed.sort(key=lambda x: x.originalIndex)
        return status, processed

    # stage 2: share remaining workload
    processed.sort(key=lambda x: pred_freq(x), reverse=True)
    idx = 0
    while allocated < agent_count and idx < len(processed):
        inst = processed[idx]
        if inst.serviceType == service_type:
            new_conn = inst.currentConnection + 1
            new_freq = inst.workloadLimit / new_conn
            new_inst = replace(
                inst,
                currentConnection=new_conn,
                currentFrequency=new_freq
            )
            if new_freq < inst.frequencyLimit[1]:
                status = "fail"
            processed[idx] = new_inst
            allocated += 1
            processed.sort(key=lambda x: pred_freq(x), reverse=True)
            idx = 0
        else:
            idx += 1

    processed.sort(key=lambda x: x.originalIndex)
    return status, processed
