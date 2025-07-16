from fastapi import FastAPI, Request
from ..application import agent_ops
from ..domain import models

app = FastAPI()

@app.post('/subscribe')
async def subscribe(request: Request):
    ar_ip = request.client.host
    host_index, port, ws_port = agent_ops.generate_agent_information()
    agent_ip = agent_ops.hosts[host_index] if agent_ops.hosts else '0.0.0.0'
    info = models.AgentInfo(ar_ip, agent_ip, port, ws_port)
    agent_ops.store_information(info)
    return {"IP": agent_ip, "Port": port, "WebsocketPort": ws_port}

@app.get('/agent')
async def get_agent(request: Request):
    ar_ip = request.client.host
    info = agent_ops.find_pair_information(ar_ip)
    if not info:
        return {"IP": "", "Port": 0, "WebsocketPort": 0}
    return {"IP": info.agent, "Port": info.agentPort, "WebsocketPort": info.websocketPort}
