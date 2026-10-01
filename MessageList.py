from openai import AsyncOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field
from copy import deepcopy
import json
import os
from sql_database.SQLClient import SQLClient, SQLiteClient
from helpers import count
from memory import MemoryClient
from prompts import system_prompts


class MessageList:
    """
    A class to store a list of messages

    Come with these features:
        - Summarization
        - Get messages as message or json strings, add messages
    """

    class SummarizeOutput(BaseModel):
        """The schema for the structured output when the agent summarizes"""
        summary: str = Field(description="The summary you made")

    class SplitOutput(BaseModel):
        """The schema for the structured output for the split agent"""
        new_summary: str = Field(description="The new shorter summary containing the most important and latest infomation from the old longer memory.")
        memories: list[str] = Field(description="A list of text chunks containing info that is not included in the new summary.")


    
    memory_client: MemoryClient
    """RAG memory client to upload new memories"""

    agent_name: str
    """The name of the agent using this message list"""

    summarize_agent: Agent
    """The agent in charge of summarize the messages"""

    split_agent: Agent
    """The agent in charge of splitting the summarization"""

    messages: list
    """The original list of messages for audit"""

    max_tokens_messages: int
    """The maximum number of tokens in the message list"""

    max_tokens_summary: int 
    """The maximum number of tokens in the summarization"""

    max_files: dict[str, int]
    """The maximum number of files in the message list"""

    modified_messages: list
    """The list of messages in json string format"""

    files_modified_messages: list
    """The list of files extracted from modified messages"""

    message_num_tokens: int
    """The current number of tokens in the modified message list"""

    num_files: int
    """The number of files extracted from the modified message list"""

    summary: str
    """The current summary"""

    sql_client: SQLClient
    """The client to get and add messages from a sql database"""

    def __init__(
            self, 
            memory_client: MemoryClient,
            max_tokens: int = 5000, 
            max_files: int = 10, 
            agent_name: str = "Alice", 
            agent_type: str = "assistant", 
            system_message: str = "Helpful assistant", 
            summarization_model: str = None
            ) -> None:
        """
        Init the list

        Init the list with the old messages from "seconds" seconds ago. Append "messages" at the end
        Save the  attributes, init the summarize agent

        Parameters:
            memory_client: the memory client given from the context to upload new memories
            max_tokens (default 5000): The maximum number of tokens in the message list
            max_files (default 5): The maximum number of files in the message list 
            agent_name (default Alice): the agent name
            agent_type (default assistant): the agent type
            system_message (default Helpful assistant): the system message of the agentges
            summarization_model: the model of the agent that summarizes the message
        """
        # Init attributes
        self.memory_client = memory_client
        self.agent_name = agent_name
        self.max_tokens_messages = int(0.7 * max_tokens)
        self.max_tokens_summary = max_tokens - self.max_tokens_messages
        self.max_files = max_files
        self.modified_messages = []
        self.files_modified_messages = []
        self.message_num_tokens = 0
        self.num_files = 0
        self.summary = ""
        self.sql_client = SQLiteClient(agent_name=agent_name, agent_type=agent_type, system_message=system_message)

        # Init summarization model
        # Get the url, api key from .env
        provider_url =  os.getenv("PROVIDER_URL")
        api_key = os.getenv("API_KEY")
        # Get the model 
        if not summarization_model:
            model = os.getenv("MODEL")
        else:
            model = summarization_model
        # Get the system prompt
        provider_client = AsyncOpenAI(base_url=provider_url,api_key=api_key)
        model_obj = OpenAIChatCompletionsModel(model=model, openai_client=provider_client)
        reasoning = Reasoning(effort="none")
        self.summarize_agent = Agent(
            name="Summarize Agent", 
            instructions=system_prompts["summarization"], 
            model=model_obj,
            output_type=self.SummarizeOutput,
            model_settings=ModelSettings(
                reasoning=reasoning
            )
        )
        self.split_agent = Agent(
            name="Split Agent", 
            instructions=system_prompts["split"], 
            model=model_obj,
            output_type=self.SplitOutput,
            model_settings=ModelSettings(
                reasoning=reasoning
            )
        )


        self.messages = []

        




    def get_messages(self) -> list:
        """Return the original messages"""
        return list(self.messages)

    def _process_message(self, message: dict) -> tuple:
        """
        Take a message dict and process it.

        Return the number of tokens and files, the files and the modified message as a string.
        The modified file has only necessary fields and without the files
        """
        # The values to return
        num_tokens = 0
        num_files = 0
        files = []
        new_message = {}

        # Create a deepcopy of the given message
        message = deepcopy(message)

        # If the messsage is an actual message, extract the role and content
        if "role" in message:
            role = message["role"]
            content = message["content"]
            # If it's a user message and content is a list, we process the list to filter out files
            if role == "user" and isinstance(content, list):
                input_items = [] 
                for input in content:
                    if input["type"] != "input_text":
                        num_files += 1
                        files.append(input)
                        # Replace the file with an input text that indicates there is a file replaced
                        input_items.append({
                            "type": "input_text",
                            "text": "There was a file here. It has been extracted and included seperately."
                        })
                    else:
                        input_items.append(input)
                content = input_items

            # Extract the role and content to create a modified message
            new_message = {"role": role, "content": content}
                
        # If it's a function call output, extract the type, call_id, output
        elif "type" in message and message["type"] == "function_call_output":
            # If it has a list as the output, process the list to extract the files
            if isinstance(message["output"], list):
                input_items = []
                for item in message["output"]:
                    # If the current item is a file
                    if item["type"] != "input_text":
                        num_files += 1
                        files.append(item)
                        # Replace the file with an input text that indicates there is a file replaced
                        input_items.append({
                            "type": "input_text",
                            "text": "There was a file here. It has been extracted and included seperately."
                        })
                    else:
                        input_items.append(item)
                message["output"] = input_items
            # Extract type, call id, output to create a new message
            new_message = {"type": message["type"], "call_id": message["call_id"], "output": message["output"]}
        # If it's a function call, extract the type, call id, name, arguments
        elif "type" in message and message["type"] == "function_call":
            new_message = {
                "type": message["type"],
                "call_id": message["call_id"],
                "name": message["name"],
                "arguments": message["arguments"]
            }
        # For other types of messages, don't modify anything
        else:
            new_message = message

        # Convert the new message to a json string and count it
        new_message_str = json.dumps(new_message)
        num_tokens = count(new_message_str)

        return num_tokens, num_files, files, new_message_str 


    async def add_messages(self, messages: list[dict], save: bool = True) -> None:
        """
        Add the messages to the end of the list.
         
        Convert the messages to json strings and files.
        Add to the lists
        Summarize if needed
        Add the messages to sql database

        Parameters:
            messages: the new messages to add
        """
        # Add the messages to the original messages list
        self.messages.extend(messages)

        if save:
            # Add the messages to the sql database
            self.sql_client.save_messages(messages)

        # Whether we need to summarize or not
        need_summarize = False

        # Convert to json strings messages and seperate files
        for message in messages:
            num_tokens, num_files, file_items, mod_message = self._process_message(message)
            self.message_num_tokens += num_tokens
            self.num_files += num_files

            # If the limit is touched , stop the converting and summarize
            if self.message_num_tokens > self.max_tokens_messages or self.num_files > self.max_files:
                need_summarize = True
                
            self.modified_messages.append(mod_message)
            self.files_modified_messages.extend(file_items)

        # Summarize if necessary
        if need_summarize:
            await self._summarize()


    async def _summarize(self) -> None:
        """
        Summarize the old messages and update the modified message list and its files list to be half of max_tokens.

        Process the original message list to count tokens and num files
        If the length of the messages is longer than max_tokens. Summarize it.
        If the length of the summarization its max tokens limit, cut the summarization in half and upload the old part to the memory
        Update the modified messages and its files
        Upload  the new memories to the recent memory collection if we need to split the summary
        """
        # Messages and files to replace the current modified messages and files
        messages = []
        all_file_items = []

        # Get the limits
        max_tokens = self.max_tokens_messages
        max_files = self.max_files
  
        current_tokens = 0
        current_files = 0

        # The id of the first message that is not added to modified messages list in the reverse messages.
        i_stop = -1

        for i, message in enumerate(reversed(self.messages)):
            num_tokens, num_files, file_items, mod_message = self._process_message(message)
            current_tokens += num_tokens
            current_files += num_files
            # If there is no message in messages yet, add it anyway
            if len(messages) == 0:
                messages.append(mod_message)
                all_file_items.extend(file_items)
                continue

            # If we don't need to execute max tokens limit or current tokens is below it, append the message
            if (max_tokens == None or current_tokens <= max_tokens / 2) and (max_files == None or current_files <= max_files / 2):
                messages.append(mod_message)
                # Prepend the file_items
                all_file_items = file_items + all_file_items
            # If num_tokens limit is exceeded, stop adding messages
            else:
                current_tokens -= num_tokens
                current_files -= num_files
                i_stop = i
                break
            
        self.message_num_tokens = current_tokens
        self.num_files = current_files
        # If nothing is dropped (one oversize message) return
        if i_stop == -1:
            return

        # Update modified messages and files attributes
        # Reverse to get the correct order
        self.modified_messages = messages[::-1]  
        self.files_modified_messages = all_file_items

        # The id of the last message that is not added to modified messages list in the original messages.
        i_stop = len(self.messages) - i_stop - 1

        

        # The prompt to send to the summarization agent
        prompt = f"""
        Summary of events before the history:
        {self.summary}
        History (Oldest to Latest):\n"""

        all_file_items = []
        for message in self.messages[:i_stop + 1]:
            num_tokens, num_files, file_items, mod_message = self._process_message(message)
            prompt += mod_message + "\n"
            all_file_items.extend(file_items)

        # The message to send to the summarization agent
        summarize_message = {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": prompt
                } 
            ] + all_file_items
        }

        result = await Runner.run(self.summarize_agent, [summarize_message], max_turns=1)
        new_part = result.final_output.summary
        self.summary = f"{self.summary}\n{new_part}" if self.summary else new_part

        # Count the new summary and split if necessary
        summary_length = count(self.summary)
        if summary_length > self.max_tokens_summary:
            prompt = f"""
            Summary:
            {self.summary}
            The new summary must be at most {self.max_tokens_summary // 2} words and each text chunk must be at most 200 words."""
            result = await Runner.run(self.split_agent, prompt)
            output = result.final_output
            self.summary = output.new_summary
            memories = output.memories

            # Upload the new memories to the recent collection
            if output.memories:
                self.memory_client.add([{"document": m} for m in memories], collection_name=f"{self.agent_name}-recent")

        # Update the original message too
        self.messages = self.messages[i_stop + 1:]


        






        

    
    