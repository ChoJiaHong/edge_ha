import asyncio
from fastapi import FastAPI
from ..application import monitor_ops

app = FastAPI()

@app.get('/nodes')
async def nodes_ready():
    data = await monitor_ops.query_prometheus('kube_node_status_condition{condition="Ready",status="true"}')
    return [ns.__dict__ for ns in await monitor_ops.parse_node_ready(data)]

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
