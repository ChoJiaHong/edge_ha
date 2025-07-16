import json
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from ..domain.models import ServiceInstance, ServiceSpec, Subscription
from ..application import service_ops

SERVICE_FILE = './Controller/information/service.json'
SERVICESPEC_FILE = './Controller/information/serviceSpec.json'
SUBSCRIPTION_FILE = './Controller/information/subscription.json'

app = FastAPI()

class SubscriptionRequest(BaseModel):
    ip: str
    port: int
    serviceType: str

@app.post('/subscribe')
async def subscribe(request: Request, subscription: SubscriptionRequest):
    try:
        with open(SERVICE_FILE, 'r') as fp:
            service_data = [ServiceInstance.from_dict(x) for x in json.load(fp)]
    except FileNotFoundError:
        service_data = []

    try:
        with open(SERVICESPEC_FILE, 'r') as fp:
            spec_data = [ServiceSpec.from_dict(x) for x in json.load(fp)]
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail='ServiceSpec file not found')

    relation_list = service_ops.compute_frequency(subscription.serviceType, 1, service_data)
    if not relation_list:
        raise HTTPException(status_code=500, detail='Unable to compute frequency')

    # simply choose first relation instance
    target = relation_list[0]
    sub = Subscription(subscription.ip, subscription.port, target.podIP, subscription.serviceType, target.nodeName)
    try:
        with open(SUBSCRIPTION_FILE, 'r') as fp:
            subs = [Subscription.from_dict(x) for x in json.load(fp)]
    except FileNotFoundError:
        subs = []
    subs.append(sub)
    with open(SUBSCRIPTION_FILE, 'w') as fp:
        json.dump([s.to_dict() for s in subs], fp, indent=4)
    with open(SERVICE_FILE, 'w') as fp:
        json.dump([s.to_dict() for s in relation_list], fp, indent=4)
    return {"IP": target.hostIP, "Port": target.hostPort, "Frequency": target.currentFrequency}

@app.post('/unsubscribe')
async def unsubscribe(request: Request):
    data = await request.json()
    agent_ip = request.client.host
    agent_port = data.get('port')
    try:
        with open(SUBSCRIPTION_FILE, 'r') as fp:
            subs = [Subscription.from_dict(x) for x in json.load(fp)]
    except FileNotFoundError:
        subs = []
    subs = [s for s in subs if not (s.agentIP == agent_ip and s.agentPort == agent_port)]
    with open(SUBSCRIPTION_FILE, 'w') as fp:
        json.dump([s.to_dict() for s in subs], fp, indent=4)
    return {'message': 'unsubscribe finish'}
