def optimize(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    Optimize the agent's transmission rate and the allocation.

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be optimized
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the optimization is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    # 儲存原始順序並初始化所需欄位
    servicelist = [
        {
            **instance,
            "originalIndex": i,
            "currentConnection": 0 if instance["serviceType"] == servicetype else instance["currentConnection"],
        }
        for i, instance in enumerate(servicelist)
    ]

    servicelist = [
        {
            **instance,
            "remainWorkload": instance["workloadLimit"] - instance["currentConnection"] * instance["frequencyLimit"][0],
            "predFreq": instance["workloadLimit"] / (instance["currentConnection"] + 1),
        }
        for instance in servicelist
    ]

    servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)

    while hasdistributed < agentcount:
        candidates = [
            (i, s) for i, s in enumerate(servicelist)
            if s["serviceType"] == servicetype and s["remainWorkload"] >= s["frequencyLimit"][0]
        ]
        if not candidates:
            break
        idx, best = max(candidates, key=lambda x: x[1]["remainWorkload"])
        new_conn = best["currentConnection"] + 1
        updated = {
            **best,
            "currentConnection": new_conn,
            "remainWorkload": best["remainWorkload"] - best["frequencyLimit"][0],
            "currentFrequency": best["frequencyLimit"][0],
            "predFreq": best["workloadLimit"] / (new_conn + 1),
        }
        servicelist = [updated if i == idx else s for i, s in enumerate(servicelist)]
        hasdistributed += 1
    # if no agent is distributed, there is no instance of the service type
    if hasdistributed == 0:
        servicelist = [
            {k: v for k, v in instance.items() if k not in ("remainWorkload", "predFreq", "originalIndex")}
            for instance in servicelist
        ]
        status = "fail"
        return status, servicelist

    # all instance is full, cannot add a agent with default transmission rate
    while hasdistributed < agentcount:
        candidates = [
            (i, s) for i, s in enumerate(servicelist) if s["serviceType"] == servicetype
        ]
        if not candidates:
            break
        idx, best = max(candidates, key=lambda x: x[1]["predFreq"])
        new_conn = best["currentConnection"] + 1
        new_freq = best["workloadLimit"] / new_conn
        if new_freq < best["frequencyLimit"][1]:
            status = "fail"
        updated = {
            **best,
            "currentConnection": new_conn,
            "currentFrequency": new_freq,
            "remainWorkload": 0,
            "predFreq": best["workloadLimit"] / (new_conn + 1),
        }
        servicelist = [updated if i == idx else s for i, s in enumerate(servicelist)]
        hasdistributed += 1

    servicelist = [
        {k: v for k, v in s.items() if k not in ("remainWorkload", "predFreq")}
        for s in servicelist
    ]

    # 恢復原本順序並移除標記欄位
    servicelist = sorted(servicelist, key=lambda x: x["originalIndex"])
    servicelist = [
        {k: v for k, v in s.items() if k != "originalIndex"}
        for s in servicelist
    ]
        
    return status, servicelist

def uniform(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    default transmission rate, agents are uniformly distributed to all service instances

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be distributed
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the distribution is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    for instance in servicelist:
        if instance["serviceType"] == servicetype:
            # clear all connection
            instance["currentConnection"] = 0
            # set the frequency to default
            instance["currentFrequency"] = instance["frequencyLimit"][0]
    while hasdistributed < agentcount:
        for instance in servicelist:
            if hasdistributed == agentcount:
                break
            if instance["serviceType"] == servicetype:
                instance["currentConnection"] += 1
                hasdistributed += 1
    return status, servicelist 

def most_remaining(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    default transmission rate, distribute the agent to the service instance that has most remaining capacity

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be distributed
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the distribution is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    for instance in servicelist:
        # clear all the current connection to redistribute
        if instance["serviceType"] == servicetype:
            instance["currentConnection"] = 0
            # set the frequency to default
            instance["currentFrequency"] = instance["frequencyLimit"][0]
        # add a field called remainWorkload
        instance["remainWorkload"] = instance["workloadLimit"] - instance["currentConnection"] * instance["frequencyLimit"][0]
    servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)

    idx = 0
    while hasdistributed < agentcount:
        if servicelist[idx]["serviceType"] == servicetype:
            servicelist[idx]["currentConnection"] += 1
            hasdistributed += 1
            servicelist[idx]["remainWorkload"] -= instance["frequencyLimit"][0]
            servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)
            idx = 0
        else:
            idx += 1
    for instance in servicelist:
        del instance["remainWorkload"]
    return status, servicelist

if __name__ == "__main__":
    service = [{
            "podIP" : "ip1",
            "hostPort" : 1,
            "serviceType" : "object",
            "currentConnection" : 10,
            "nodeName" : "nodename",
            "hostIP" : "hostip",
            "frequencyLimit" : [5,3],
            "currentFrequency" : 1,
            "workloadLimit" : 5
        },{
            "podIP" : "ip2",
            "hostPort" : 2,
            "serviceType" : "object",
            "currentConnection" : 20,
            "nodeName" : "nodename",
            "hostIP" : "hostip",
            "frequencyLimit" : [5,3],
            "currentFrequency" : 1,
            "workloadLimit" : 50
        }]

    status, servicelist = optimize("object", 101, service)

    print(servicelist)
    print(status)