from openai import AsyncOpenAI
from agents import Agent, Runner, trace, function_tool, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field
from copy import deepcopy
import json
from sql_database.SQLClient import SQLClient, SQLiteClient
from helpers import count


class MessageList:
    """
    A class to store a list of messages

    Come with these features:
        - Summarization
        - Get messages as message or json strings, add messages
    """

    messages: list
    """The original list of messages"""

    max_tokens: dict[str, int]
    """The maximum number of tokens in the message list"""

    max_files: dict[str, int]
    """The maximum number of files in the message list"""

    sql_client: SQLClient
    """The client to get and add messages from a sql database"""

    def __init__(self, max_tokens: int = 5000, max_files: int = 5, agent_name: str = "Alice", agent_type: str = "assistant", system_message: str = "Helpful assistant", seconds: int = 60*60*24, messages: list = None) -> None:
        """
        Init the list

        Init the list with the old messages from "seconds" seconds ago. Append "messages" at the end

        Parameters:
            max_tokens (default 5000): The maximum number of tokens in the message list
            max_files (default 5): The maximum number of files in the message list 
            agent_name (default Alice): the agent name
            agent_type (default assistant): the agent type
            system_message (default Helpful assistant): the system message of the agent
            seconds (default 1 day): the number of seconds ago to retrieve the old messages
            messages (optional): A list of messages to append at the end of the list of messages seconds ago retrieved from the db
        """
        pass

    def get_messages(self) -> list:
        """Return the original messages"""
        return self.messages

    def _process_message(message: dict) -> tuple:
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

    def fetch_modified_messages(self) -> tuple:
        """
        Return the modified latest messages without embedded files as json strings with at most max_tokens tokens/words and max_file files (at least 1 message even if length > n)

        Fetch data from all input sources whose attention is not none. 
        Combine with existing messages and return the messages as a list and the files
        If a limit is None, then ignore that limit
        """


        # Messages and files to return
        messages = []
        all_file_items = []

        # Get the limits
        max_tokens = self.max_tokens
        max_files = self.max_files

        current_tokens = 0
        current_files = 0
        

        for message in reversed(self.messages):
            num_tokens, num_files, file_items, mod_message = self._process_message(message)
            current_tokens += num_tokens
            current_files += num_files
            # If there is no message in messages yet, add it anyway
            if len(messages) == 0:
                messages.append(mod_message)
                all_file_items.extend(file_items)
                continue

            # If we don't need to execute max tokens limit or current tokens is below it, append the message
            if max_tokens == None or current_tokens <= max_tokens:
                messages.append(mod_message)
            # If num_tokens limit is exceeded, stop adding messages
            else:
                break
            
            # If we don't need to execute max files limit or current number of files is below it, append the files
            if max_files == None or current_files <= max_files:
                all_file_items.extend(file_items)
            # If num_files limit is exceeded, just ignore the files and still add string messages if num_tokens is not exceeded

        # Reverse to get the correct order
        messages = reversed(messages)        
        return messages, all_file_items

    def add_messages(self, messages: list) -> None:
        """
        Add the messages to the end of the list. Summarize if needed

        Parameters:
            messages: the new messages to add
        """
        pass

    def _summarize(self) -> None:
        """
        If the length of the messages is longer than max_tokens. Summarize it.

        Summarize to reduce the length to half of max_tokens
        """
        pass

    
    