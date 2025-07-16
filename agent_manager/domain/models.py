from dataclasses import dataclass

@dataclass
class AgentInfo:
    AR: str
    agent: str
    agentPort: int
    websocketPort: int
