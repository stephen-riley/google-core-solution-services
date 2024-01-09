# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Agent classes """
import re
from abc import ABC, abstractmethod
from typing import Union, Type, Callable, List, Optional

from langchain.agents import (Agent, AgentOutputParser,
                              ConversationalAgent)
from langchain.agents.structured_chat.base import StructuredChatAgent
from langchain.agents.structured_chat.output_parser \
    import StructuredChatOutputParserWithRetries
from langchain.agents.structured_chat.prompt \
    import FORMAT_INSTRUCTIONS as STRUCTURED_FORMAT_INSTRUCTIONS
from langchain.agents.conversational.prompt import FORMAT_INSTRUCTIONS
from langchain.schema import AgentAction, AgentFinish
from config.utils import get_dataset_config
from common.models import QueryEngine
from common.models.agent import AgentCapability
from common.utils.http_exceptions import InternalServerError
from common.utils.logging_handler import Logger
from services import langchain_service
from services.agents.agent_prompts import (PREFIX, ROUTING_PREFIX,
                                           TASK_PREFIX, PLANNING_PREFIX,
                                           PLAN_FORMAT_INSTRUCTIONS,
                                           ROUTING_FORMAT_INSTRUCTIONS)
from services.agents.agent_tools import (gmail_tool, docs_tool, database_tool,
                                         google_sheets_tool,
                                         calendar_tool, search_tool,
                                         query_tool)

Logger = Logger.get_logger(__file__)

class BaseAgent(ABC):
  """
  Base Agent for LLM Service agents.  All agents are based on Langchain
  agents and basically specify the configuration for a particular variant
  of Langchain agent.
  """

  llm_type: str = None
  """ the LLM Service llm type used to power the agent """

  agent: Agent = None
  """ the langchain agent instance """

  agent_class: Type[Agent] = None
  """ the langchain agent class """

  name:str = None
  """ The name of the agent """

  prefix: str = PREFIX
  """ The prefix prompt of the agent """

  def __init__(self, llm_type: str):
    self.llm_type = llm_type
    self.agent = None

  def set_prefix(self, prefix) -> str:
    self.prefix = prefix


  @property
  def format_instructions(self) -> str:
    return FORMAT_INSTRUCTIONS

  @property
  def output_parser_class(self) -> Type[AgentOutputParser]:
    raise NotImplementedError(
        "Derived classes should provide output_parser_class")

  @classmethod
  @abstractmethod
  def capabilities(cls) -> List[str]:
    """ return capabilities of this agent class """

  @abstractmethod
  def get_tools(self) -> List[Callable]:
    """ return tools used by this agent """

  def load_agent(self, input_variables: Optional[List[str]] = None) -> Agent:
    """ load this agent and return an instance of langchain Agent"""
    tools = self.get_tools()

    llm = langchain_service.get_model(self.llm_type)
    if llm is None:
      raise InternalServerError(
          f"Agent: cannot find LLM type {self.llm_type}")

    output_parser = self.output_parser_class()
    self.agent = self.agent_class.from_llm_and_tools(
        llm=llm,
        tools=tools,
        prefix=self.prefix,
        format_instructions=self.format_instructions,
        output_parser=output_parser,
        input_variables=input_variables
    )
    Logger.info(f"Successfully loaded {self.name} agent.")
    Logger.debug(f"prefix=[{self.prefix}], "
                 f"format_instructions=[{self.format_instructions}]",
                 f"input_variables=[{input_variables}]")
    return self.agent

  @classmethod
  def get_query_engines(cls, agent_name, agent_params: dict) -> \
      List[QueryEngine]:
    """ 
    Get list of query engines available to this agent.  Agent
    query engines can be configured in agent config, or tagged
    in query engine data models.
    """
    agent_query_engines = []

    if "query_engines" in agent_params:
      agent_qe_names = agent_params["query_engines"].split(",")
      agent_qe_names = [qe.strip() for qe in agent_qe_names]
      agent_query_engines = QueryEngine.collection.filter(
        "name", "in", agent_qe_names).fetch()

    tagged_query_engines = QueryEngine.collection.filter(
        agent_name, "in", "agents"
    ).fetch()
    tagged_query_engines = tagged_query_engines or []

    query_engines = agent_query_engines | tagged_query_engines
    return query_engines

  @classmethod
  def get_datasets(cls, agent_params) -> dict:
    """
    Agent datasets are configured in agent config
    """
    agent_datasets = {}
    agent_dataset_names = []
    if "datasets" in agent_params:
      agent_dataset_names = agent_params["datasets"].split(",")
      agent_dataset_names = [ds.strip() for ds in agent_dataset_names]
    datasets = get_dataset_config()
    agent_datasets = {
      ds_name: ds_config for ds_name, ds_config in datasets.items()
      if ds_name in agent_dataset_names
    }
    return agent_datasets


class ChatAgent(BaseAgent):
  """
  Chat Agent.  This is an agent configured for basic informational chat with a
  human.  It includes search and query tools.
  """
  def __init__(self, llm_type: str):
    super().__init__(llm_type)
    self.name = "ChatAgent"
    self.agent_class = ConversationalAgent

  @property
  def output_parser_class(self) -> Type[AgentOutputParser]:
    return ToolAgentOutputParser

  @classmethod
  def capabilities(cls) -> List[str]:
    """ return capabilities of this agent class """
    capabilities = [AgentCapability.AGENT_CHAT_CAPABILITY,
                    AgentCapability.AGENT_QUERY_CAPABILITY]
    return capabilities

  def get_tools(self) -> List[Callable]:
    """ return tools used by this agent """
    return [search_tool, query_tool]


class RoutingAgent(BaseAgent):
  """
  Routing Agent.  This is an agent configured for dispatching
  a given prompt to the best route with given list of choices.
  """
  def __init__(self, llm_type: str):
    super().__init__(llm_type)
    self.name = "RoutingAgent"
    self.agent_class = ConversationalAgent
    self.prefix = ROUTING_PREFIX

  @property
  def output_parser_class(self) -> Type[AgentOutputParser]:
    return RoutingAgentOutputParser

  @property
  def format_instructions(self) -> str:
    return ROUTING_FORMAT_INSTRUCTIONS

  @classmethod
  def capabilities(cls) -> List[str]:
    """ return capabilities of this agent class """
    capabilities = [AgentCapability.AGENT_CHAT_CAPABILITY,
                    AgentCapability.AGENT_QUERY_CAPABILITY]
    return capabilities

  def get_tools(self) -> List[Callable]:
    """ return tools used by this agent """
    return []


class TaskAgent(BaseAgent):
  """
  Structured Task Agent.  This agent accepts multiple inputs and can call
  StructuredTools that accept multiple inputs,not just one String. This is an
  agent configured to execute tasks on behalf of a human.  Every task has a
  plan, consisting of plan steps. Creation of the plan is done by a planning
  agent.
  """

  def __init__(self, llm_type: str):
    super().__init__(llm_type)
    self.name = "TaskAgent"
    self.agent_class = StructuredChatAgent

  def load_agent(self,input_variables: Optional[List[str]] = None) -> Agent:
    """ load this agent and return an instance of langchain Agent"""
    #This is the list of variables defined in the associated prompt
    #input_variables = ["input", "user", "user_email", "task_plan",
    # "agent_scratchpad"]
    return super().load_agent()

  @property
  def prefix(self) -> str:
    return TASK_PREFIX

  @property
  def output_parser_class(self) -> Type[AgentOutputParser]:
    return StructuredChatOutputParserWithRetries

  @property
  def format_instructions(self) -> str:
    return STRUCTURED_FORMAT_INSTRUCTIONS
  @classmethod
  def capabilities(cls) -> List[str]:
    """ return capabilities of this agent class """
    capabilities = [AgentCapability.AGENT_CHAT_CAPABILITY,
                    AgentCapability.AGENT_QUERY_CAPABILITY,
                    AgentCapability.AGENT_TASK_CAPABILITY]
    return capabilities

  def get_tools(self):
    tools = [gmail_tool, database_tool,  google_sheets_tool, docs_tool,
      calendar_tool, search_tool, query_tool]
    return tools

  def get_planning_agent(self) -> str:
    """
    This is the agent used by this agent to create plans for tasks.
    """
    return "PlanAgent"


class PlanAgent(BaseAgent):
  """
  Plan Agent.  This is an agent configured to make plans.
  Plans will be executed using a different agent.
  """

  def __init__(self, llm_type: str):
    super().__init__(llm_type)
    self.name = "PlanAgent"
    self.agent_class = StructuredChatAgent
    self.prefix = PLANNING_PREFIX

  @property
  def format_instructions(self) -> str:
    return PLAN_FORMAT_INSTRUCTIONS

  @property
  def output_parser_class(self) -> Type[AgentOutputParser]:
    return PlanAgentOutputParser

  @classmethod
  def capabilities(cls) -> List[str]:
    """ return capabilities of this agent class """
    capabilities = [AgentCapability.AGENT_PLAN_CAPABILITY]
    return capabilities

  def get_tools(self):
    tools = [gmail_tool, database_tool, google_sheets_tool, docs_tool,
      calendar_tool, search_tool, query_tool]
    return tools


class RoutingAgentOutputParser(AgentOutputParser):
  """Output parser for a agent that makes plans."""

  ai_prefix: str = "AI"
  """Prefix to use before AI output."""

  def get_format_instructions(self) -> str:
    return ROUTING_FORMAT_INSTRUCTIONS

  def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
    regex = r"Action: (.*?)[\n]*Action Input: (.*)"
    match = re.search(regex, text)
    if not match:
      # TODO: undo this temporary fix to make the v1 agent terminate
      #raise OutputParserException(
      #    f"MIRA: Could not parse LLM output: `{text}`")
      return AgentFinish(
          {
            "output": text.split(f"{self.ai_prefix}:")[-1].strip()
          }, text
      )
    action = match.group(1)
    action_input = match.group(2)
    return AgentAction(action.strip(),
                       action_input.strip(" ").strip('"'), text)

  @property
  def _type(self) -> str:
    return "zero_shot"


class PlanAgentOutputParser(AgentOutputParser):
  """Output parser for a agent that makes plans."""

  ai_prefix: str = "AI"
  """Prefix to use before AI output."""

  def get_format_instructions(self) -> str:
    return PLAN_FORMAT_INSTRUCTIONS

  def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
    if f"{self.ai_prefix}:" in text:
      return AgentFinish(
          {"output": text.split(f"{self.ai_prefix}:")[-1].strip()}, text
      )
    regex = r"Action: (.*?)[\n]*Action Input: (.*)"
    match = re.search(regex, text)
    if not match:
      # TODO: undo this temporary fix to make the v1 agent terminate
      #raise OutputParserException(
      #    f"MIRA: Could not parse LLM output: `{text}`")
      return AgentFinish(
          {"output": text.split(f"{self.ai_prefix}:")[-1].strip()}, text
      )
    action = match.group(1)
    action_input = match.group(2)
    return AgentAction(action.strip(),
                       action_input.strip(" ").strip('"'), text)

  @property
  def _type(self) -> str:
    return "zero_shot"


class ToolAgentOutputParser(AgentOutputParser):
  """Output parser for a conversational agent that uses tools."""

  ai_prefix: str = "AI"
  """Prefix to use before AI output."""

  def get_format_instructions(self) -> str:
    return FORMAT_INSTRUCTIONS

  def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
    if f"{self.ai_prefix}:" in text:
      return AgentFinish(
          {"output": text.split(f"{self.ai_prefix}:")[-1].strip()}, text
      )
    print(f"[ToolAgentOutputParser] text: {text}")
    regex = r"Action: (.*?)[\n]*Action Input: (.*)"
    match = re.search(regex, text)
    if not match:
      # TODO: undo this temporary fix to make the v1 agent terminate
      #raise OutputParserException(
      #    f"MIRA: Could not parse LLM output: `{text}`")
      return AgentFinish(
          {"output": text.split(f"{self.ai_prefix}:")[-1].strip()}, text
      )
    action = match.group(1)
    action_input = match.group(2)
    return AgentAction(action.strip(),
                       action_input.strip(" ").strip('"'), text)

  @property
  def _type(self) -> str:
    return "conversational"

