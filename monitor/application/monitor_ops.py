import requests
import asyncio
from ..domain import models

PROMETHEUS_URL = 'http://prometheus-stack-kube-prom-prometheus.prometheus.svc.cluster.local:9090/api/v1/query'

async def query_prometheus(query: str):
    resp = requests.get(PROMETHEUS_URL, params={'query': query})
    if resp.status_code == 200:
        return resp.json()
    return None

async def parse_node_ready(data) -> list[models.NodeStatus]:
    nodes = []
    if not data:
        return nodes
    for result in data.get('data', {}).get('result', []):
        node = result['metric']['node']
        status = 'Ready' if result['value'][1] == '1' else 'NotReady'
        nodes.append(models.NodeStatus(node, status))
    return nodes
