from typing import List, Tuple
import json
import os
from . import models

PAIR_FILE = 'AR_Agent.json'

current_host = 0
port_counter = 8888
ws_counter = 50051
hosts: List[str] = []
accounts: List[str] = []
passwords: List[str] = []

def configure(host_list: List[str], account_list: List[str], password_list: List[str]):
    global hosts, accounts, passwords
    hosts = host_list
    accounts = account_list
    passwords = password_list


def generate_agent_information() -> Tuple[int, int, int]:
    global current_host, port_counter, ws_counter, hosts
    host_index = current_host
    current_host = (current_host + 1) % len(hosts) if hosts else 0
    port_counter += 1
    ws_counter += 1
    return host_index, port_counter - 1, ws_counter - 1


def store_information(info: models.AgentInfo) -> None:
    if os.path.exists(PAIR_FILE):
        with open(PAIR_FILE, 'r') as fp:
            data = json.load(fp)
    else:
        data = []
    # remove old
    data = [d for d in data if d.get('AR') != info.AR]
    data.append({
        'AR': info.AR,
        'Agent': info.agent,
        'AgentPort': info.agentPort,
        'AgentWebsocketPort': info.websocketPort
    })
    with open(PAIR_FILE, 'w') as fp:
        json.dump(data, fp)


def find_pair_information(ar: str) -> models.AgentInfo | None:
    if not os.path.exists(PAIR_FILE):
        return None
    with open(PAIR_FILE, 'r') as fp:
        data = json.load(fp)
    for d in data:
        if d['AR'] == ar:
            return models.AgentInfo(d['AR'], d['Agent'], d['AgentPort'], d['AgentWebsocketPort'])
    return None
