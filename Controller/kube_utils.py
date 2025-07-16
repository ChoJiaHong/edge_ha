import json
import time
import logging
import yaml
import concurrent.futures
from typing import List

import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .config import IN_CLUSTER, NODE_STATUS_FILE


def get_node_ip(node_name: str) -> str:
    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        raise

    core_api = client.CoreV1Api()

    try:
        node = core_api.read_node(name=node_name)
        for address in node.status.addresses:
            if address.type == "InternalIP":
                return address.address
        print("InternalIP not found")
        return "Error"
    except client.exceptions.ApiException as e:
        print(f"Exception when calling CoreV1Api->read_node: {e}")
        return "Error"


def curl_health_check(ip: str):
    url = f"http://{ip}:10248/healthz"
    try:
        response = requests.get(url, timeout=1)
        if response.status_code == 200:
            return response.text
        return f"Health check failed for {url}. Status Code: {response.status_code}"
    except requests.exceptions.Timeout:
        return f"Request to {url} timed out. The URL may not exist."
    except requests.exceptions.RequestException as e:
        return f"An error occurred while trying to reach {url}: {e}"


def deploy_pod(service_type, hostPort, node_name):
    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        logging.error(f"Error loading kubeconfig: {e}")
        raise

    core_api = client.CoreV1Api()

    try:
        with open(f"service_yaml/{service_type}.yaml") as f:
            dep = yaml.safe_load(f)
    except Exception as e:
        print("Service Type YAML file not found")
        logging.error("Service Type YAML file not found")
        raise

    unique_name = f"{service_type}-{str(node_name)}-{str(hostPort)}"
    dep['metadata']['name'] = unique_name
    dep['spec']['containers'][0]['ports'][0]['hostPort'] = hostPort
    dep['spec']['nodeSelector'] = {'kubernetes.io/hostname': node_name}

    if is_pod_terminating(core_api, unique_name):
        logging.warning(f"Pod {unique_name} is terminating, changing hostPort...")
        return None

    try:
        resp = core_api.create_namespaced_pod(body=dep, namespace='default')
        logging.info(f"Send the request of deploying Pod {resp.metadata.name}.")
    except ApiException as e:
        logging.error(f"Exception when deploying Pod: {e}")
        raise

    while True:
        resp = core_api.read_namespaced_pod(name=unique_name, namespace='default')
        if resp.spec.node_name and resp.status.pod_ip and resp.status.host_ip:
            break
        time.sleep(0.5)
    return resp


def communicate_with_agent(data: dict, agent_ip: str, agent_port: int):
    url = f"http://{agent_ip}:{agent_port}/servicechange"
    try:
        response = requests.post(url, data=json.dumps(data))
        logging.info(f"communicate with Agent {agent_ip} {agent_port}, body = {data}")
        return response.status_code, response.text
    except requests.exceptions.RequestException as e:
        return None, str(e)


def delete_pod(pod_name, namespace='default'):
    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        logging.error(f"Error loading kubeconfig: {e}")
        raise

    core_api = client.CoreV1Api()

    try:
        core_api.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            print(f"Failed to delete Pod: {e}")


def node_status_sync(node_name_list: List[str]):
    node_health_status = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_node = {}
        for node_name in node_name_list:
            ip = get_node_ip(node_name)
            if ip != "Error":
                future = executor.submit(curl_health_check, ip)
                future_to_node[future] = node_name
            else:
                node_health_status[node_name] = "unhealthy"
        for future in concurrent.futures.as_completed(future_to_node):
            node_name = future_to_node[future]
            try:
                health_status = future.result()
                if health_status.strip().lower() == 'ok':
                    node_health_status[node_name] = "healthy"
                else:
                    node_health_status[node_name] = "unhealthy"
            except Exception:
                node_health_status[node_name] = "unhealthy"
    with open(NODE_STATUS_FILE, 'w') as node_status_file:
        json.dump(node_health_status, node_status_file, indent=4)
    return json.dumps(node_health_status, indent=4)


def is_pod_terminating(core_api, pod_name, namespace="default"):
    try:
        resp = core_api.read_namespaced_pod(name=pod_name, namespace=namespace)
        if resp.metadata.deletion_timestamp:
            return True
    except ApiException as e:
        if e.status == 404:
            return False
        logging.error(f"Error checking pod status: {e}")
    return False
