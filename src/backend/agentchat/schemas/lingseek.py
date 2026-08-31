from typing import List, Any
from pydantic import BaseModel


class LingSeekGuidePrompt(BaseModel):
    query: str
    model_id: str = ""
    web_search: bool = True
    plugins: List[str] = []
    mcp_servers: List[str] = []
    file_urls: List[str] = []


class LingSeekGuidePromptFeedBack(BaseModel):
    query: str
    guide_prompt: str
    feedback: str = ""
    model_id: str = ""
    web_search: bool = True
    plugins: List[str] = []
    mcp_servers: List[str] = []
    file_urls: List[str] = []

class LingSeekTask(BaseModel):
    query: str
    guide_prompt: str
    model_id: str = ""
    web_search: bool = True
    plugins: List[str] = []
    mcp_servers: List[str] = []
    file_urls: List[str] = []

class LingSeekTaskStep(BaseModel):
    thought: str
    step_id: str
    title: str
    target: str
    workflow: Any
    precautions: str
    input_thought: str
    input: List[str] = []

    result: str = ""


class LingSeekStepRetry(BaseModel):
    """单节点重试请求：携带完整步骤定义与已有结果，仅重跑 retry_step_id 对应节点"""
    query: str
    guide_prompt: str
    model_id: str = ""
    web_search: bool = True
    plugins: List[str] = []
    mcp_servers: List[str] = []
    file_urls: List[str] = []
    steps: List[LingSeekTaskStep] = []
    retry_step_id: str