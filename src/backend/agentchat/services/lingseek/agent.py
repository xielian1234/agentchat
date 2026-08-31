import json
from typing import List, Union, Optional

from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage, AIMessageChunk
from langchain_core.utils.function_calling import convert_to_openai_tool

from agentchat.api.services.mcp_server import MCPService
from agentchat.api.services.mcp_user_config import MCPUserConfigService
from agentchat.api.services.usage_stats import UsageStatsService
from agentchat.api.services.workspace_session import WorkSpaceSessionService
from agentchat.core.callbacks import usage_metadata_callback
from agentchat.database.models.workspace_session import WorkSpaceSessionCreate, WorkSpaceSessionContext
from agentchat.prompts.template import GuidePromptTemplate
from agentchat.schemas.workspace import WorkSpaceAgents
from agentchat.schemas.usage_stats import UsageStatsAgentType
from agentchat.core.agents.mcp_agent import MCPConfig
from agentchat.tools import LingSeekPlugins, tavily_search as web_search
from agentchat.api.services.tool import ToolService
from agentchat.core.models.manager import ModelManager
from agentchat.utils.convert import mcp_tool_to_args_schema, convert_mcp_config
from agentchat.utils.date_utils import get_beijing_time
from agentchat.services.mcp.manager import MCPManager
from agentchat.prompts.lingseek import GenerateGuidePrompt, FeedBackGuidePrompt, GenerateTitlePrompt, \
    GenerateTaskPrompt, FixJsonPrompt, ToolCallPrompt, SystemMessagePrompt
from agentchat.schemas.lingseek import LingSeekGuidePrompt, LingSeekGuidePromptFeedBack, LingSeekTask, \
    LingSeekTaskStep, LingSeekStepRetry
from agentchat.services.workspace.file_attachment import build_query_with_attachments


class LingSeekAgent:
    def __init__(self, user_id: str, model_config: Optional[dict] = None):
        self.mcp_manager: Optional[MCPManager] = None
        self.mcp_tools = []
        self.tool_mcp_server_dict = {}

        self.user_id = user_id

        # 优先使用用户选择的模型（model_config）；未选择时回退到 config.yaml 中的默认配置
        if model_config:
            self.conversation_model = ModelManager.get_user_model(**model_config)
            self.tool_call_model = ModelManager.get_user_model(**model_config)
        else:
            self.conversation_model = ModelManager.get_conversation_model()
            self.tool_call_model = ModelManager.get_lingseek_intent_model()

    async def _augment_query(self, query: str, file_urls: List[str]) -> str:
        """把附件内容拼进问题里，让灵寻的各阶段都能读到附件文本。"""
        if not file_urls:
            return query
        return await build_query_with_attachments(query, file_urls)

    async def _generate_guide_prompt(self, lingseek_guide_prompt):
        """
        通过COT的方法使得模型回复的更加准确，但是展示的时候需要把思考内容隐藏
        """
        one = None
        sop_flag = False
        sop_content = ""
        answer = ""
        split_tags = ["<Thought_END>", "</Thought_END>"]
        async for one in self.conversation_model.astream(input=lingseek_guide_prompt, config={"callbacks": [usage_metadata_callback]}):
            answer += f"{one.content}"
            if sop_flag:
                yield one
                sop_content += one.content
                continue
            for split_tag in split_tags:
                if answer.find(split_tag) != -1:
                    sop_flag = True
                    sop_content = answer.split(split_tag)[-1].strip()
                    if sop_content:
                        one.content = sop_content
                        yield one
                    break
        if not sop_content:
            one.content = answer
            yield one

    async def _generate_tasks(self, lingseek_task_prompt):
        conversation_json_model = self.conversation_model.bind(response_format={"type": "json_object"})

        response = await conversation_json_model.ainvoke(input=lingseek_task_prompt, config={"callbacks": [usage_metadata_callback]})

        try:
            content = json.loads(response.content)
            return content
        except Exception as err:
            fix_message = FixJsonPrompt.format(json_content=response.content, json_error=str(err))
            fix_response = await conversation_json_model.ainvoke(input=fix_message, config={"callbacks": [usage_metadata_callback]})
            try:
                fix_content = json.loads(fix_response.content)
                return fix_content
            except Exception as fix_err:
                raise ValueError(fix_err)

    async def _generate_title(self, query):
        title_prompt = GenerateTitlePrompt.format(query=query)
        response = await self.conversation_model.ainvoke(input=title_prompt, config={"callbacks": [usage_metadata_callback]})
        return response.content

    async def _add_workspace_session(self, query, contexts: WorkSpaceSessionContext):
        title = await self._generate_title(query)
        await WorkSpaceSessionService.create_workspace_session(
            WorkSpaceSessionCreate(
                title=title,
                user_id=self.user_id,
                contexts=[contexts.model_dump()],
                agent=WorkSpaceAgents.LingSeekAgent.value))

    async def _parse_function_call_response(self, message: AIMessage):
        tool_messages = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args")
                tool_call_id = tool_call.get("id")

                content = await self._process_tools_result(tool_name, tool_args)
                tool_messages.append(ToolMessage(content=content, name=tool_name, tool_call_id=tool_call_id))

        return tool_messages

    async def generate_tasks(self, lingseek_task: LingSeekTask):
        tools = await self._obtain_lingseek_tools(lingseek_task.plugins, lingseek_task.mcp_servers, lingseek_task.web_search)
        tools_str = json.dumps(tools, ensure_ascii=False, indent=2)

        query = await self._augment_query(lingseek_task.query, lingseek_task.file_urls)

        lingseek_task_prompt = GenerateTaskPrompt.format(
            tools_str=tools_str,
            query=query,
            guide_prompt=lingseek_task.guide_prompt,
            current_time=get_beijing_time(),
        )

        response_task = await self._generate_tasks(lingseek_task_prompt)
        return response_task

    async def generate_guide_prompt(self, lingseek_info: Union[LingSeekGuidePrompt, LingSeekGuidePromptFeedBack],
                                    feedback: bool = False):

        tools = await self._obtain_lingseek_tools(lingseek_info.plugins, lingseek_info.mcp_servers, lingseek_info.web_search)
        tools_str = json.dumps(tools, ensure_ascii=False, indent=2)

        query = await self._augment_query(lingseek_info.query, lingseek_info.file_urls)

        if feedback:
            lingseek_guide_prompt = FeedBackGuidePrompt.format(
                query=query,
                tools_str=tools_str,
                feedback=lingseek_info.feedback,
                feedback_guide_prompt=lingseek_info.guide_prompt,
            )
        else:
            lingseek_guide_prompt = GenerateGuidePrompt.format(
                tools_str=tools_str,
                query=query,
                guide_prompt_template=GuidePromptTemplate,
            )
        async for chunk in self._generate_guide_prompt(lingseek_guide_prompt):
            yield {
                "event": "generate_guide_prompt",
                "data": {
                    "chunk": chunk.content
                }
            }


    async def submit_lingseek_task(self, lingseek_task: LingSeekTask):
        task = await self.generate_tasks(lingseek_task)

        query = await self._augment_query(lingseek_task.query, lingseek_task.file_urls)

        tasks_graph = {}
        tasks_show = []
        steps_payload = []
        steps = task.get("steps", [])
        for step in steps:
            task_step = LingSeekTaskStep(**step)
            tasks_graph[task_step.step_id] = task_step
            steps_payload.append(task_step.model_dump())

        for step_id, step_info in tasks_graph.items():
            for input_step in step_info.input:
                if input_step in tasks_graph:
                    # 构建展示的任务列表图结构
                    tasks_show.append({
                        "start": tasks_graph[input_step].title,
                        "end": tasks_graph[step_id].title
                    })
                else:
                    tasks_show.append({
                        "start": "用户问题",
                        "end": tasks_graph[step_id].title
                    })
        yield {
            "event": "generate_tasks",
            "data": {"graph": tasks_show, "steps": steps_payload}
        }


        tools = await self._obtain_lingseek_tools(lingseek_task.plugins, lingseek_task.mcp_servers, lingseek_task.web_search)
        tool_call_model = self.tool_call_model.bind_tools(tools) if len(tools) else self.tool_call_model

        messages: List[BaseMessage] = [SystemMessage(content=SystemMessagePrompt), HumanMessage(content=query)]
        context_task = []
        for step_id, step_info in tasks_graph.items():
            step_context = []
            for input_step in step_info.input:
                if input_step in tasks_graph:
                    step_context.append(
                        tasks_graph[input_step].model_dump()
                    )

            yield {
                "event": "step_start",
                "data": {"step_id": step_info.step_id, "title": step_info.title}
            }

            step_status = "completed"
            step_error = ""
            try:
                response, tools_messages, result = await self._execute_step_tools(
                    tool_call_model, step_info, step_context, query)
                step_info.result = result
            except Exception as err:
                logger.error(f"步骤「{step_info.title}」执行失败: {err}")
                response = None
                tools_messages = []
                step_info.result = ""
                step_status = "failed"
                step_error = str(err)

            context_task.append(step_info.model_dump())
            if response is not None:
                if tools_messages:  # 合到整体Messages
                    messages.append(response)
                    messages.extend(tools_messages)
                else:
                    messages.append(HumanMessage(content=query))
                    messages.append(AIMessage(content=response.content))

            yield {
                "event": "step_result",
                "data": {
                    "step_id": step_info.step_id,
                    "title": step_info.title,
                    "message": step_info.result or " ",
                    "status": step_status,
                    "error": step_error,
                    "thought": step_info.thought,
                    "target": step_info.target,
                    "workflow": step_info.workflow,
                    "precautions": step_info.precautions,
                    "input_thought": step_info.input_thought,
                }
            }

        final_response = ""
        async for chunk in self.conversation_model.astream(messages):
            final_response += chunk.content
            yield {
                "event": "task_result",
                "data": {"message": chunk.content}
            }

        await self._add_workspace_session(
            lingseek_task.query,
            WorkSpaceSessionContext(
                query=lingseek_task.query,
                guide_prompt=lingseek_task.guide_prompt,
                task=context_task,
                task_graph=tasks_show,
                answer=final_response,
                model_id=lingseek_task.model_id,
                web_search=lingseek_task.web_search,
                plugins=lingseek_task.plugins,
                mcp_servers=lingseek_task.mcp_servers,
            ))

    async def _execute_step_tools(self, tool_call_model, step_info: LingSeekTaskStep, step_context, query: str):
        step_prompt = ToolCallPrompt.format(
            step_info=step_info,
            step_context=str(step_context)
        )
        step_messages = [SystemMessage(content=step_prompt), HumanMessage(content=query)]
        response = await tool_call_model.ainvoke(input=step_messages, config={"callbacks": [usage_metadata_callback]})
        tools_messages = await self._parse_function_call_response(response)
        result = "\n".join([msg.content for msg in tools_messages])
        return response, tools_messages, result

    async def retry_step(self, lingseek_step_retry: LingSeekStepRetry):
        step_map = {s.step_id: s for s in lingseek_step_retry.steps}
        retry_step = step_map.get(lingseek_step_retry.retry_step_id)
        if retry_step is None:
            yield {
                "event": "step_result",
                "data": {
                    "step_id": lingseek_step_retry.retry_step_id,
                    "title": "",
                    "message": "",
                    "status": "failed",
                    "error": "未找到该节点",
                }
            }
            return

        tools = await self._obtain_lingseek_tools(lingseek_step_retry.plugins, lingseek_step_retry.mcp_servers, lingseek_step_retry.web_search)
        tool_call_model = self.tool_call_model.bind_tools(tools) if len(tools) else self.tool_call_model

        step_context = [step_map[i].model_dump() for i in retry_step.input if i in step_map]

        query = await self._augment_query(lingseek_step_retry.query, lingseek_step_retry.file_urls)

        yield {
            "event": "step_start",
            "data": {"step_id": retry_step.step_id, "title": retry_step.title}
        }

        step_status = "completed"
        step_error = ""
        try:
            _, _, result = await self._execute_step_tools(
                tool_call_model, retry_step, step_context, query)
            retry_step.result = result
        except Exception as err:
            logger.error(f"重试步骤「{retry_step.title}」失败: {err}")
            step_status = "failed"
            step_error = str(err)

        yield {
            "event": "step_result",
            "data": {
                "step_id": retry_step.step_id,
                "title": retry_step.title,
                "message": retry_step.result or " ",
                "status": step_status,
                "error": step_error,
                "thought": retry_step.thought,
                "target": retry_step.target,
                "workflow": retry_step.workflow,
                "precautions": retry_step.precautions,
                "input_thought": retry_step.input_thought,
            }
        }

        # 基于（更新后的）所有步骤结果重新生成最终答案
        final_messages = self._build_final_answer_messages(query, lingseek_step_retry.steps)
        async for chunk in self.conversation_model.astream(final_messages):
            yield {
                "event": "task_result",
                "data": {"message": chunk.content}
            }

    def _build_final_answer_messages(self, query: str, steps: List[LingSeekTaskStep]):
        parts = []
        for s in steps:
            parts.append(f"### 步骤：{s.title}\n{s.result or '（无结果）'}")
        summary = "\n\n".join(parts)
        return [
            SystemMessage(content=SystemMessagePrompt),
            HumanMessage(content=query),
            HumanMessage(content=f"以下是各步骤的执行结果，请据此给出最终答案：\n\n{summary}"),
        ]

    async def _process_tools_result(self, tool_name, tool_args):
        def find_mcp_tool(tool_name):
            """Find MCP tool by name"""
            for tool in self.mcp_tools:
                if tool.name == tool_name:
                    return tool
            return None

        if tool := find_mcp_tool(tool_name):
            mcp_config = await MCPUserConfigService.get_mcp_user_config(self.user_id,
                                                                        self.tool_mcp_server_dict[tool_name])
            tool_args.update(mcp_config)
            text_content, no_text_content = await tool.coroutine(**tool_args)
        else:
            text_content = LingSeekPlugins[tool_name].invoke(tool_args)
        return text_content

    async def _obtain_lingseek_tools(self, plugins, mcp_servers, enable_web_search=False):
        plugins_name = await ToolService.get_tool_name_by_id(plugins)
        plugins_func = []
        for name in plugins_name:
            func = LingSeekPlugins.get(name)
            if func is None:
                logger.warning(f"插件 {name} 未在 LingSeekPlugins 中注册，已跳过")
                continue
            plugins_func.append(func)

        tools = [convert_to_openai_tool(func) for func in plugins_func]

        if enable_web_search and web_search not in plugins_func:
            plugins_func.append(web_search)
            tools.append(convert_to_openai_tool(web_search))

        async def get_mcp_tools():
            if self.mcp_tools:
                return self.mcp_tools

            servers_config = []
            for mcp_id in mcp_servers:
                mcp_server = await MCPService.get_mcp_server_from_id(mcp_id)
                mcp_config = MCPConfig(**mcp_server)

                self.tool_mcp_server_dict.update({tool: mcp_config.mcp_server_id for tool in mcp_config.tools})
                servers_config.append(
                    convert_mcp_config(mcp_config.model_dump())
                )
            self.mcp_manager = MCPManager(servers_config)
            mcp_tools = await self.mcp_manager.get_mcp_tools()
            self.mcp_tools = mcp_tools

            return mcp_tools

        mcp_tools = await get_mcp_tools()
        mcp_tools = [mcp_tool_to_args_schema(tool.name, tool.description, tool.args_schema) for tool in mcp_tools]
        tools.extend(mcp_tools)

        return tools

    async def _record_agent_token_usage(self, response: AIMessage | AIMessageChunk | BaseMessage, model):
        if response.usage_metadata:
            await UsageStatsService.create_usage_stats(
                model=model,
                user_id=self.user_id,
                agent=UsageStatsAgentType.lingseek_agent,
                input_tokens=response.usage_metadata.get("input_tokens"),
                output_tokens=response.usage_metadata.get("output_tokens")
            )