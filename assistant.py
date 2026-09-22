from openai import AsyncOpenAI
from agents import Agent, Runner, trace, function_tool, OpenAIChatCompletionsModel, ModelSettings
from agents.mcp import MCPServerStdio, MCPServerManager
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field
import gradio as gr
import asyncio
import time
from datetime import datetime
import uuid
import json
from dotenv import load_dotenv
import prompts
from sources import GradioUI
from context import Context
load_dotenv(override=True)


"""
with open('personas.json', mode='r', encoding='utf-8') as f:
            personas = json.load(f)
        self.persona_name =  personas['chosen_persona']
        self.persona = personas[self.persona_name]
"""

# FIXME: add_response should get an increment response in case a message is added while the model is streaming
class Assistant:
    on: bool
    """Whether the agent is on or off"""

    # Time when call start()
    start_time = 0
    # Seconds between each loop of modules
    unit_time = 0.1

    context: Context
    """The context object for the agent"""

    
    model_obj: OpenAIChatCompletionsModel
    """The reasoning model object"""

    agent: Agent
    """The agent object"""


    def __init__(
            self, 
            input_source_names: list[str] = ["chat_gradio"], 
            output_source_names: list[str] = ["chat_gradio"], 
            model="qwen3.8-gsq-vision:latest", 
            agent_type: str = "assistant", 
            url: str = "http://localhost:11434/v1", 
            api_key: str = "api_key", 
            reasoning: str = "none") -> None:
        """
        Initialize the agent

        Inputs:
            input_source_name: The str names of the input sources that the agent will use
            output_source_name: The str names of the output sources that the agent will send to
            model: the AI model to use
            agent_type: the type of the agent (assistant, subagent,...)
            url: the url to call the model, default to ollama
            api_key: the api_key of the provider
            reasoning: the reasoning effort
        """
        # Temporary set to time when call init, later will be overidden when call start()
        self.start_time = time.perf_counter()
        self.unit_time = 0.1

        # Create the gradio object beforehand if it's in input or output sources name
        if "chat_gradio" in input_source_names + output_source_names:
            gradio_ui = GradioUI()

        # Initialize input sources
        input_sources = {}
        for name in input_source_names:
            if name == "chat_gradio":
                input_sources[name] = gradio_ui.input_source

        # Initialize the output sources
        output_sources = {}
        for name in output_source_names:
            if name == "chat_gradio":
                output_sources[name] = gradio_ui.output_source

        self.context = Context(input_sources=input_sources, output_sources=output_sources, agent_type=agent_type)
                

        # Init model objects and agents
        provider_client = AsyncOpenAI(base_url=url,api_key=api_key)
        self.model_obj = OpenAIChatCompletionsModel(model=model, openai_client=provider_client)
        # Init reasoning_agent with essential tools
        # FIXME: Add tools and mcp servers to context and use them from context
        mcp_params = {
            "command": "uvx",
            "args": ["windows-mcp", "serve"],
            "env": {"WINDOWS_MCP_SCREENSHOT_SCALE": "0.3"}
        }
        self.mcp_servers = [MCPServerStdio(
            name="filesystem",
            params=mcp_params,
            cache_tools_list=True,
            client_session_timeout_seconds=120,
        )]

        reasoning = Reasoning(effort=reasoning)
        self.agent = Agent(
            name="Reasoning Agent", 
            instructions=self.context.system_prompt, 
            model=self.model_obj, 
            tools=self.list_tools(), 
            model_settings=ModelSettings(
                reasoning=reasoning
            ),
            tool_use_behavior="stop_on_first_tool"
        )

    # Wrapper function which provides self parameter to tools and return them
    # FIXME: implement thought tool which add the tool call to self.messages
    def list_tools(self):
        # FIXME: implement think tool
        @function_tool
        def think(reasoning: str):
            """
            A tool to reasoning. 
            
            If you want to reason, call this function and give your reasoning as the argument
            This tool is for recording your reasoning only, it doesn't return anything.
            Your reasonings here are not visible to the user
            Do not output your reasoning directly
            DO NOT INGORE THIS TOOL. YOU MUST USE THIS WHEN NECESSARY (COMPLEX TASKS, QUERIES). 
            THIS IS PLACE FOR YOU TO DO REASONING.
            """
            self.log(reasoning, mode="a", file_path="reasoning_log.txt")
            return ""

        @function_tool
        async def wait(n: int = 10):
            """
            Wait up to n seconds for the user to say something. 
            Used once you finished the latest request from the user and want to wait for them.
            You should tell the user that you have finished first and then wait for them.
            Recommended waiting strategy:
                - Increase the wait time if you receive no messages after several wait calls.
                - You must use this tool if the user keeps not sending any messages. DO NOT LET YOURSELF BE INVOKED CONTINUOUSLY WITH NO GOALS.

            Input:
                n: the number of seconds to wait
            """
            self.log(f"wait called with {n} seconds", mode="a")

            # The number of seconds have passed
            secs_passed = 0

            # Wait until time out or there are new data from input sources
            while secs_passed < n and not self.context.input_sources.has_new():
                await asyncio.sleep(1)
                secs_passed += 1
            return f"{secs_passed} seconds have passed"
         
        return [wait, think]

    # HELPERS
    # Count the number of words/tokens. Currently words
    def count(self, str: str):
        return len(str.split(' '))
    
    # Log to log.txt
    def log(self, text, file_path: str = "log.txt", mode: str = "w"):
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(f"{text}\n")
    

    # Start the agent
    async def start(self):
        """
        Start a loop to continuosly invoke the agent. Only stop when self.on set to False by other routines
        """

        # FIXME: change 
        # Init mcp
        async with MCPServerManager(self.mcp_servers) as manager:
            self.agent.mcp_servers = manager.active_servers
            self.on = True
            while self.on:
                context = self.context.fetch_messages()
                self.log(context, file_path="agent_logs.txt")
                try:
                    result = Runner.run_streamed(self.agent, context, max_turns=1)
                    # Stream the output
                    async for event in result.stream_events():
                        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                            # Send the streaming phrase to output sources that use streaming
                            self.context.send_phrase(event.data.delta)  # assistant text, token by token
                        # elif event.type == "run_item_stream_event":
                        #     if event.name == "tool_called":
                        #         call = event.item.raw_item
                        #         print(f"\n[tool call] {call.name}({call.arguments})")
                        #     elif event.name == "tool_output":
                        #         print(f"[tool result] {event.item.output}")
                    
                    # Send the end of response phrase to signify the end of the current response for streaming
                    self.context.send_phrase("||END_OF_RESPONSE||")
                    # Send the complete messages list to context and output sources that use complete messages
                    print(str(result.to_input_list()))

                    # Send only the newly produced messages to context
                    self.context.send_messages(result.to_input_list()[len(messages):])

                    # Wait 

                except Exception as e:
                    print(f'Error: {e}')

                
            
