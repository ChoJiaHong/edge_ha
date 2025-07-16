from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import json
from kubernetes import client, config
from starlette.responses import JSONResponse
import logging
import asyncio

from config import (
    GPU_MEMORY_LABEL,
    IN_CLUSTER,
    SERVICE_FILE,
    SERVICESPEC_FILE,
    SUBSCRIPTION_FILE,
    NODE_STATUS_FILE,
    LOG_FILE,
)
from service_manager import compute_frequnecy, adjust_frequency
from kube_utils import (
    get_node_ip,
    curl_health_check,
    deploy_pod,
    communicate_with_agent,
    delete_pod,
    node_status_sync,
    is_pod_terminating,
)

locked = False


# 設定 logging，將所有日誌寫入到 LOG_FILE
logging.basicConfig(
    filename= LOG_FILE,
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO
)

class SubscriptionRequest(BaseModel):
    ip: str
    port: int
    serviceType: str
    
def lifespan(app: FastAPI):
    # 初始化 NODE_STATUS_FILE
    config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    core_api = client.CoreV1Api()
    node_status_list = []

    # 獲取所有節點的標籤
    nodes = core_api.list_node().items
    for node in nodes:
        labels = node.metadata.labels
        if labels.get('arha-node-type') == 'computing-node':
            node_status_list.append(node.metadata.name)

    node_health_status = {}
    for node in node_status_list:
        ip = get_node_ip(node)
        if ip != "Error":
            try:
                if curl_health_check(ip).strip().lower() == 'ok':
                    node_health_status[node] = "healthy"
                else:
                    node_health_status[node] = "unhealthy"
            except Exception as e:
                node_health_status[node] = "unhealthy"
        else:
            node_health_status[node] = "unhealthy"

    with open(NODE_STATUS_FILE, 'w') as node_status_file:
        json.dump(node_health_status, node_status_file, indent=4)
    yield 

app = FastAPI(lifespan=lifespan)

# 中間件，用來紀錄每個 API 呼叫的詳情
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 取得 API 名稱 (路徑)、請求內容、來源 IP
    api_name = request.url.path
    request_body = await request.body()
    client_ip = request.client.host  # 取得來源 IP
    request_log = request_body.decode("utf-8") if request_body else None
    logging.info(f"{api_name} receive request {request_log} from IP: {client_ip}")

    # 呼叫 API 並取得回應
    try:
        response = await call_next(request)
        response_body = b"".join([chunk async for chunk in response.body_iterator])
        status_code = response.status_code  # 取得狀態碼
        response = JSONResponse(content=json.loads(response_body), status_code=status_code)
    except Exception as e:
        status_code = 500
        response = JSONResponse(content={"error": str(e)}, status_code=status_code)
    
    # 組合 log 訊息
    log_message = {
        "api_name": api_name,
        "client_ip": client_ip,  # 新增來源 IP 記錄
        "request": request_body.decode("utf-8") if request_body else None,
        "response": response.body.decode("utf-8"),
        "status_code": status_code  # 新增狀態碼記錄
    }
    response_log = response.body.decode("utf-8")
    # 將 log 訊息寫入到日誌檔
    # logging.info(json.dumps(log_message))
    logging.info(f"{api_name} response {response_log} and status code: {status_code}")
    
    return response

@app.post('/subscribe') # 接收訂閱請求
async def subscribe(request: Request, subscription: SubscriptionRequest):
    data = subscription
    agent_ip = data.ip
    agent_port = data.port
    serviceType = data.serviceType
    serviceNotFound = True

    if not agent_ip or not serviceType:
        raise HTTPException(status_code=400, detail="Invalid input")

    # 檢查請求中的serviceType是否存在
    try:
        with open(SERVICESPEC_FILE, 'r') as serviceSpec_jsonFile:
            try:
                serviceSpec_data = json.load(serviceSpec_jsonFile)
                for serviceSpec in serviceSpec_data:
                    if serviceSpec['serviceType'] == serviceType:
                        serviceNotFound = False
                        break
                if (serviceNotFound):
                    raise HTTPException(status_code=500, detail="Service not in serviceSpec file")
            except json.decoder.JSONDecodeError: 
                raise HTTPException(status_code=500, detail="ServiceSpec file is empty")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ServiceSpec file not found")

    global locked
    while locked:
        await asyncio.sleep(1)

    locked = True
    agentCounter = 1
    with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
        try:
            subscription_list = json.load(subscription_jsonFile)
        except json.decoder.JSONDecodeError: 
            subscription_list = []
    
    agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == serviceType)
    relation_list = compute_frequnecy(serviceType, agentCounter)

    newAgentCounter = 0
    for relation in relation_list:
        if relation['serviceType'] == serviceType:
            newAgentCounter += int(relation['currentConnection'])
    
    if newAgentCounter == (agentCounter-1):
        locked = False
        return 'reject the subscription' 
    elif newAgentCounter == agentCounter:
        with open(SERVICE_FILE, 'w') as service_jsonFile:
            json.dump(relation_list, service_jsonFile, indent=4)

        # 這邊adjust_frequency只會調整new agent以外的配對關係
        serviceIndex = adjust_frequency(serviceType)

        with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
            try:
                subscription_list = json.load(subscription_jsonFile)
            except json.decoder.JSONDecodeError: 
                subscription_list = []

        if serviceIndex is None:
            locked = False
            logging.info(f"Function adjust_frequency() return None")
            return 'controller program bug'
        else:
            subscription_list.append({
                "agentIP": agent_ip,
                "agentPort": agent_port,
                "podIP": relation_list[serviceIndex]['podIP'],
                "serviceType": serviceType,
                "nodeName": relation_list[serviceIndex]['nodeName']            
            })
        with open(SUBSCRIPTION_FILE, 'w') as subscription_jsonFile:
            json.dump(subscription_list, subscription_jsonFile, indent=4)
            locked = False
            return {
                "IP": relation_list[serviceIndex]['hostIP'],
                "Port": relation_list[serviceIndex]['hostPort'],
                "Frequency": relation_list[serviceIndex]['currentFrequency']
            }
    else:
        locked = False
        return f"newAgentCounter={newAgentCounter} and agentCounter={agentCounter}" 

@app.post('/alert')
async def alert(request: Request):

    global locked
    while locked:
        await asyncio.sleep(1)
    locked = True    
    data = await request.json()
    alertType = data['alertType']
    alertContent = data['alertContent']

    # 處理Computing Node 故障的Case
    if alertType == 'workernode_failure':
        
        failnodeName = alertContent['nodeName']

        # 將故障的Computing Node上的所有服務從資料中清除
        try:
            with open(SERVICE_FILE, 'r') as service_file:
                try:
                    service_list = json.load(service_file)
                except json.decoder.JSONDecodeError:
                    service_list = []
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="Service file not found")
        
        failed_service_list = [item for item in service_list if item.get('nodeName') == failnodeName]
        service_list = [item for item in service_list if item.get('nodeName') != failnodeName]

        try:
            with open(SERVICE_FILE, 'w') as service_file:
                json.dump(service_list, service_file, indent=4)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to write to service file")

        # 處理故障節點上的所有service
        for failed_service in failed_service_list:
            
            # 從k8s中刪除service
            delete_pod(str(failed_service['serviceType'])+'-'+str(failed_service['nodeName'])+'-'+str(failed_service['hostPort']),'default')
            
            # 打開訂閱資料
            try:
                with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
                    try:
                        subscription_list = json.load(subscription_jsonFile)
                    except json.decoder.JSONDecodeError:
                        subscription_list = []
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="Subscription file not found")
            
            # 若沒有任何終端訂閱故障service
            if failed_service['currentConnection'] == 0:
                continue

            # 若有終端訂閱故障之service
            agentCounter = 0
            agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == failed_service['serviceType'])
            relation_list = compute_frequnecy(str(failed_service['serviceType']), agentCounter)

            # 計算最後有多少Agent能使用服務 
            newAgentCounter = 0
            for relation in relation_list:
                if relation['serviceType'] == str(failed_service['serviceType']):
                    newAgentCounter += int(relation['currentConnection'])

            # 若非所有Agent都能使用服務
            if newAgentCounter < agentCounter:
                count = 0
                unsunscribedAgentCounter = agentCounter - newAgentCounter
                for i in reversed(range(len(subscription_list))):
                    if subscription_list[i]['podIP'] == str(failed_service['podIP']):
                        del subscription_list[i]
                        count += 1
                        if count >= unsunscribedAgentCounter:
                            break
                with open(SUBSCRIPTION_FILE, 'w') as subscription_file:
                    json.dump(subscription_list, subscription_file, indent=4)

            # 將新的配對方式存入service_file中
            with open(SERVICE_FILE, 'w') as service_file:
                json.dump(relation_list, service_file, indent=4)                
            adjust_frequency(str(failed_service['serviceType']))        
    elif alertType == 'pod_failure':

        failPodName = str(alertContent['podName'])
        serviceType, nodeName, hostPort = failPodName.split('-')
        hostPort = int(hostPort)
        delete_pod(failPodName)

        with open(SERVICE_FILE, 'r') as service_file:
            try:
                service_list = json.load(service_file)
            except json.decoder.JSONDecodeError:
                service_list = []

        # 找到符合條件的元素
        failed_service = next(
            (service for service in service_list if 
                service['serviceType'] == serviceType and 
                service['nodeName'] == nodeName and 
                service['hostPort'] == hostPort), 
            None  # 若找不到，返回 None
        )

        # 如果找到，則從 service_list 刪除
        if failed_service:
            service_list.remove(failed_service)

        with open(SERVICE_FILE, 'w') as service_file:
            json.dump(service_list, service_file, indent=4)

        if failed_service['currentConnection'] != 0:

            # 打開訂閱資料
            try:
                with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
                    try:
                        subscription_list = json.load(subscription_jsonFile)
                    except json.decoder.JSONDecodeError:
                        subscription_list = []
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="Subscription file not found")
            
            agentCounter = 0
            agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == failed_service['serviceType'])
            relation_list = compute_frequnecy(str(failed_service['serviceType']), agentCounter)

            # 計算最後有多少Agent能使用服務 
            newAgentCounter = 0
            for relation in relation_list:
                if relation['serviceType'] == str(failed_service['serviceType']):
                    newAgentCounter += int(relation['currentConnection'])

            # 若非所有Agent都能使用服務
            if newAgentCounter < agentCounter:
                count = 0
                unsunscribedAgentCounter = agentCounter - newAgentCounter
                for i in reversed(range(len(subscription_list))):
                    if subscription_list[i]['podIP'] == str(failed_service['podIP']):
                        del subscription_list[i]
                        count += 1
                        if count >= unsunscribedAgentCounter:
                            break
                with open(SUBSCRIPTION_FILE, 'w') as subscription_file:
                    json.dump(subscription_list, subscription_file, indent=4)

            with open(SERVICE_FILE, 'w') as service_file:
                json.dump(relation_list, service_file, indent=4)

        adjust_frequency(str(failed_service['serviceType']))  
    locked = False
    return (f"message: Alert {alertType} handled successfully")

@app.post('/deploypod')
async def deploypod(request: Request):
    data = await request.json()
    node_name = str(data['nodeName'])
    hostPort = int(data['hostPort'])
    service_type = str(data['service_type'])
    serviceamountonnode = int(data['amount'])
    resp = deploy_pod(service_type,hostPort, node_name)

    try:
        with open(SERVICE_FILE, 'r') as service_jsonFile:
            try:
                service_data = json.load(service_jsonFile)
            except json.decoder.JSONDecodeError: # 要是當前集群中沒有任何Pod
                service_data = []
    except FileNotFoundError:
        return "Service file not found"

    with open(SERVICESPEC_FILE, 'r') as serviceSpec_jsonFile:
        serviceSpec_list = json.load(serviceSpec_jsonFile)
    
    for serviceSpec in serviceSpec_list:
        if serviceSpec['serviceType'] == service_type:
            workloadLimit = serviceSpec['workAbility'][node_name]
            frequencyLimit = serviceSpec['frequencyLimit']
    """        
    if  service_type == 'pose':
        if node_name == 'workergpu':
            workloadLimit = 70
        else:
            workloadLimit = 85
        frequencyLimit = [20,10]
    else:
        frequencyLimit = [30,15]
        if node_name == 'workergpu':
            workloadLimit = 170
        else:
            workloadLimit = 255
    """
    service_data.append({
        "podIP" : str(resp.status.pod_ip),
        "hostPort" : int(hostPort),
        "serviceType" : service_type,
        "currentConnection" : 0,
        "nodeName" : str(node_name),
        "hostIP" : str(resp.status.host_ip),
        "frequencyLimit" : frequencyLimit,
        "currentFrequency" : frequencyLimit[0],
        "workloadLimit" : workloadLimit/serviceamountonnode        
    })

    with open(SERVICE_FILE, 'w') as service_file:
        json.dump(service_data, service_file, indent=4)     

    return 'deploy finish'

@app.post('/unsubscribe')
async def unsubscribe(request: Request):
    data = await request.json()
    agent_ip = request.client.host
    agent_port = data['port']

    try:
        with open(SUBSCRIPTION_FILE, 'r') as subscription_jsonFile:
            try:
                subscription_data = json.load(subscription_jsonFile)
            except json.decoder.JSONDecodeError:
                subscription_data = []
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail= "Subscription file not found")
    
    new_subscription_data = []
    podip_set = set()

    for subscription in subscription_data:
        if str(subscription['agentIP']) == str(agent_ip) and int(subscription['agentPort']) == int(agent_port):
            podip_set.add(subscription['podIP'])
            message = "unsubscribe successfully"
        else:
            new_subscription_data.append(subscription)

    try:
        with open(SUBSCRIPTION_FILE, 'w') as subscription_file:
            json.dump(new_subscription_data, subscription_file, indent=4)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to write to subscription file")
    
    try:
        with open(SERVICE_FILE, 'r') as service_jsonFile:
            try:
                service_data = json.load(service_jsonFile)
            except json.decoder.JSONDecodeError: # 要是當前集群中沒有任何Pod
                raise HTTPException(status_code=404, detail= "Service file is empty")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail= "Service file not found")
    
    for service in service_data:
        # 更新服務當前的連線數
        if service['podIP'] in podip_set:
            service['currentConnection'] -=1 

    with open(SERVICE_FILE, 'w') as service_jsonFile:
        json.dump(service_data, service_jsonFile, indent=4)

    return {'message' : 'unsubscribe finish'}

