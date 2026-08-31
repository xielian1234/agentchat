from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from agentchat.core.callbacks import usage_metadata_callback
from agentchat.core.models.manager import ModelManager


class StructuredResponseAgent:
    def __init__(self, response_format, model=None):
        self.response_format = response_format
        self.structured_agent = self._create_structured_agent(model)

    def _create_structured_agent(self, model=None):
        return create_agent(
            model=model or ModelManager.get_conversation_model(),
            response_format=ToolStrategy(self.response_format)
        )

    def get_structured_response(self, messages):
        result = self.structured_agent.invoke(
            input={"messages": messages},
            config={"callbacks": [usage_metadata_callback]}
        )
        return result["structured_response"]