import json
import copy
import logging
import time
import os

from typing import List

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .config import (
    SERVICE_FILE,
    SERVICESPEC_FILE,
    SUBSCRIPTION_FILE,
    NODE_STATUS_FILE,
    GPU_MEMORY_LABEL,
    IN_CLUSTER,
)
from .kube_utils import (
    deploy_pod,
    node_status_sync,
    communicate_with_agent,
)
import optimizer

# select optimizer function by environment variable
optimize = getattr(optimizer, os.getenv("OPTIMIZER_FUNCTION", "optimize"))


def compute_frequnecy(serviceType: str, agentCounter: int):
    mustAutoScaling = True
    with open(SERVICE_FILE, 'r') as service_jsonFile:
        try:
            service_list = json.load(service_jsonFile)
        except json.decoder.JSONDecodeError:
            service_list = []
    for service in service_list:
        if service['serviceType'] == serviceType:
            mustAutoScaling = False
    if not mustAutoScaling:
        status, relation_list = optimize(serviceType, agentCounter, service_list)
        for relation in relation_list:
            if relation['currentFrequency'] < relation['frequencyLimit'][0]:
                mustAutoScaling = True
                break
    if mustAutoScaling:
        deploy_service(serviceType)
        with open(SERVICE_FILE, 'r') as service_jsonFile:
            try:
                service_list = json.load(service_jsonFile)
            except json.decoder.JSONDecodeError:
                service_list = []
        status, relation_list = optimize(serviceType, agentCounter, service_list)
        while status == 'fail':
            agentCounter -= 1
            status, relation_list = optimize(serviceType, agentCounter, service_list)
    return relation_list


def deploy_service(serviceType: str):
    nodeDeployed_list = []
    workloadLimitAfterDeployed_dict = {}
    serviceSpec_dict = {}
    usedPort = set()
    with open(SERVICESPEC_FILE, 'r') as serviceSpec_jsonFile:
        serviceSpec_list = json.load(serviceSpec_jsonFile)
    for serviceSpec in serviceSpec_list:
        nodeDeployed_list.extend(serviceSpec["workAbility"].keys())
        serviceSpec_dict[serviceSpec['serviceType']] = {
            k: v for k, v in serviceSpec.items() if k != "serviceType"
        }
    nodeDeployed_list = list(set(nodeDeployed_list))
    config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    core_api = client.CoreV1Api()
    with open(SERVICE_FILE, 'r') as service_jsonFile:
        try:
            service_list = json.load(service_jsonFile)
        except json.decoder.JSONDecodeError:
            service_list = []
    node_status_sync(nodeDeployed_list)
    with open(NODE_STATUS_FILE, 'r') as node_status_jsonFile:
        node_status_data = json.load(node_status_jsonFile)
    for nodeDeployed in nodeDeployed_list:
        if node_status_data[nodeDeployed] == 'unhealthy':
            continue
        canDeployOnThisNode = True
        gpuMemoryRequest = 0
        serviceTypeOnThisNode_list = []
        for service in service_list:
            if service['nodeName'] == nodeDeployed:
                if service['serviceType'] == serviceType:
                    canDeployOnThisNode = False
                    break
                else:
                    serviceTypeOnThisNode_list.append(service['serviceType'])
                    gpuMemoryRequest += serviceSpec_dict[service['serviceType']]['gpuMemoryRequest']
        nodeInformation = core_api.read_node(name=nodeDeployed)
        gpuMemory = int(nodeInformation.metadata.labels.get(GPU_MEMORY_LABEL))
        if not canDeployOnThisNode or gpuMemoryRequest > gpuMemory:
            continue
        for serviceTypeOnThisNode in serviceTypeOnThisNode_list:
            workloadLimitAfterDeployed = float(
                serviceSpec_dict[serviceTypeOnThisNode]['workAbility'][nodeDeployed]
            ) / (len(serviceTypeOnThisNode_list)+1)
            if workloadLimitAfterDeployed < serviceSpec_dict[serviceTypeOnThisNode]['frequencyLimit'][0]:
                canDeployOnThisNode = False
                break
        if float(serviceSpec_dict[serviceType]['workAbility'][nodeDeployed]) / (
            len(serviceTypeOnThisNode_list)+1) < serviceSpec_dict[serviceType]['frequencyLimit'][0]:
            canDeployOnThisNode = False
        if canDeployOnThisNode:
            workloadLimitAfterDeployed_dict[nodeDeployed] = float(
                serviceSpec_dict[serviceType]['workAbility'][nodeDeployed]
            ) / (len(serviceTypeOnThisNode_list)+1)
    if len(workloadLimitAfterDeployed_dict) == 0:
        return 'no enoungh computing resource'
    workloadLimit = max(workloadLimitAfterDeployed_dict.values())
    nodeName = next(
        iter(k for k, v in workloadLimitAfterDeployed_dict.items() if v == workloadLimit)
    )
    serviceTypeOnThisNode = 1
    serviceTypeOnThisNode += sum(1 for service in service_list if service['nodeName'] == nodeName)
    serviceConnection_dict = {}
    indexOfServiceOnDeployedNode = []
    for index, service in enumerate(service_list):
        if service['nodeName'] == nodeName:
            indexOfServiceOnDeployedNode.append(index)
        if service['serviceType'] not in serviceConnection_dict:
            serviceConnection_dict[service['serviceType']] = 0
        serviceConnection_dict[service['serviceType']] += int(service['currentConnection'])
        usedPort.add(int(service['hostPort']))
    adjustFrequencyServiceType_list = []
    for index in indexOfServiceOnDeployedNode:
        service_list[index]['workloadLimit'] = serviceSpec_dict[service_list[index]['serviceType']]['workAbility'][nodeName] / (
            len(indexOfServiceOnDeployedNode)+1)
        originalService_list = copy.deepcopy(service_list)
        status, service_list = optimize(
            service_list[index]['serviceType'],
            serviceConnection_dict[service_list[index]['serviceType']],
            service_list,
        )
        if status == 'fail':
            return 'no enoungh computing resource'
        if service_list != originalService_list:
            adjustFrequencyServiceType_list.append(service_list[index]['serviceType'])
    with open(SERVICE_FILE, 'w') as service_jsonFile:
        json.dump(service_list, service_jsonFile, indent=4)
    for adjustFrequencyServiceType in adjustFrequencyServiceType_list:
        adjust_frequency(adjustFrequencyServiceType)
    for i in range(30500, 31000):
        if i not in usedPort:
            hostPort = i
            break
    resp = deploy_pod(serviceType, hostPort, nodeName)
    while resp is None:
        for i in range(hostPort+1, 31000):
            if i not in usedPort:
                hostPort = i
                break
        resp = deploy_pod(serviceType, hostPort, nodeName)
    podIP = resp.status.pod_ip
    hostIP = resp.status.host_ip
    nodeName = resp.spec.node_name
    podName = resp.metadata.name
    timeCounter = 0
    isPodReady = False
    while not isPodReady:
        pod = core_api.read_namespaced_pod(name=podName, namespace='default')
        for data in pod.status.conditions:
            if data.type == 'Ready' and data.status == 'True':
                isPodReady = True
        if timeCounter == 12:
            break
        if not isPodReady:
            time.sleep(5)
            timeCounter += 1
    service_list.append({
        "podIP": str(podIP),
        "hostPort": int(hostPort),
        "serviceType": str(serviceType),
        "currentConnection": 0,
        "nodeName": nodeName,
        "hostIP": str(hostIP),
        "frequencyLimit": serviceSpec_dict[serviceType]['frequencyLimit'],
        "currentFrequency": serviceSpec_dict[serviceType]['frequencyLimit'][0],
        "workloadLimit": serviceSpec_dict[serviceType]['workAbility'][nodeName] / float(len(indexOfServiceOnDeployedNode)+1)
    })
    with open(SERVICE_FILE, 'w') as service_jsonFile:
        json.dump(service_list, service_jsonFile, indent=4)
    logging.info(f"deploy {serviceType} service successfully")
    return f"deploy {serviceType} service successfully"


def adjust_frequency(serviceType: str):
    podIPIndex_dict = {}
    with open(SERVICE_FILE, 'r') as service_jsonFile:
        try:
            service_list = json.load(service_jsonFile)
        except json.decoder.JSONDecodeError:
            service_list = []
    with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
        try:
            subscription_list = json.load(subscription_jsonFile)
        except json.decoder.JSONDecodeError:
            subscription_list = []
    for index, service in enumerate(service_list):
        if service['serviceType'] == serviceType:
            podIPIndex_dict[service['podIP']] = {}
            podIPIndex_dict[service['podIP']]['index'] = index
            podIPIndex_dict[service['podIP']]['currentConnection'] = service['currentConnection']
            podIPIndex_dict[service['podIP']]['currentFrequency'] = service['currentFrequency']
            podIPIndex_dict[service['podIP']]['nodeName'] = service['nodeName']
    reconfigureAgentIndex_list = []
    for index, subscription in enumerate(subscription_list):
        if (
            subscription['podIP'] in podIPIndex_dict.keys() and
            podIPIndex_dict[subscription['podIP']]['currentConnection'] != 0 and
            subscription['serviceType'] == serviceType
        ):
            podIPIndex_dict[subscription['podIP']]['currentConnection'] -= 1
            body = {
                'servicename': serviceType,
                'ip': 'null',
                'port': 0,
                'frequency': service_list[podIPIndex_dict[subscription['podIP']]['index']]['currentFrequency'],
            }
            communicate_with_agent(body, str(subscription['agentIP']), int(subscription['agentPort']))
        elif subscription['serviceType'] == serviceType:
            reconfigureAgentIndex_list.append(index)
            if subscription['podIP'] in podIPIndex_dict.keys():
                del podIPIndex_dict[subscription['podIP']]
    for reconfigureAgentIndex in reconfigureAgentIndex_list:
        for key, value in podIPIndex_dict.items():
            if int(value['currentConnection']) != 0:
                value['currentConnection'] -= 1
                body = {
                    'servicename': serviceType,
                    'ip': str(service_list[value['index']]['hostIP']),
                    'port': int(service_list[value['index']]['hostPort']),
                    'frequency': service_list[value['index']]['currentFrequency'],
                }
                communicate_with_agent(
                    body,
                    str(subscription_list[reconfigureAgentIndex]['agentIP']),
                    int(subscription_list[reconfigureAgentIndex]['agentPort']),
                )
                subscription_list[reconfigureAgentIndex]['podIP'] = str(key)
                subscription_list[reconfigureAgentIndex]['nodeName'] = str(service_list[value['index']]['nodeName'])
                break
    with open(SUBSCRIPTION_FILE, 'w') as subscription_jsonFile:
        json.dump(subscription_list, subscription_jsonFile, indent=4)
    for key, value in podIPIndex_dict.items():
        if int(value['currentConnection']) != 0:
            logging.info(
                f"Function adjust_frequency() adjust frequency of {serviceType} and return {value['index']}"
            )
            return value['index']
    logging.info(f"Function adjust_frequency() adjust frequency of {serviceType}")
    return None
