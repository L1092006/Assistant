import gradio as gr
from typing import Literal
from abc import ABC, abstractmethod
from copy import deepcopy, copy
import asyncio


class InputSource(ABC):
    """Base class for an input source for the agent to fetch input. Contains basic state and its fetch state method as well as init the source"""

    state: object
    """Contains all the input data from the source for audit"""

    new_data: object
    """New data in from the source that has not been consumed yet"""

    _attention: Literal["full", "simple", "none"]
    """
    Attention setting for the input source
    Possible values: full | simple | none
    - full: fetch() returns all new state data
    - simple: Some sources may not use it. If simple is set, the new state data is simplified before being returned in fetch()
    - none: fetch() return nothing
    """

    allowed_attentions = ["full", "simple", "none"]
    """Class attribute which  defined the allowed value of _attention"""

    connected: bool
    """Check if the input source is being connected to be used or not"""

    def __init__(self, state: object = None, new_data: object  = None, attention: Literal["full", "simple", "none"] = "full"):
        """Initialize the object"""
        self.state = deepcopy(state)
        self.new_data = deepcopy(new_data)

        # Check if attetion is one of the three allowed string
        if attention not in ["full", "simple", "none"]:
            raise ValueError(f"Attention must be one of 'full', 'simple', or 'none'. Got '{attention}' instead.")
        self.attention = deepcopy(attention)
        self.connected = False

    @abstractmethod
    def fetch(self) -> None:
        """Consume new_data and extend state with new data."""
        pass

    def connect(self) -> None:
        """Connect to the input source"""
        self.connected = True

    @abstractmethod
    def add_data(self) -> None:
        """For the source to add new data if connected and attention is not none"""
        pass
    
    @abstractmethod
    def has_new(self) -> bool:
        """
        Indicate if there is new data in state that has not been consumed yet.

        The implementation must return True if:
        - There is new_data is not empty
        - self.attention is not none
        """
        pass

    @property
    def attention(self):
        return self._attention

    @attention.setter
    def attention(self, attention):
        """Setter for attentions. Ensure only allowed values are set"""
        if attention not in InputSource.allowed_attentions:
            raise ValueError(f"Invalid attention")
        self._attention = attention

class MessageInputSource(InputSource):
    """
    Base class for input sources that send input as a list of messages in ResponseAPI format.
    
    Characteristics:
        state and new_data are lists of messages (dict)
        connect() doesn't do anything, just set connected to True
    """
    state: list[dict]
    new_data: list[dict]
    """state and new data should be a list of dict in ResponseAPI format"""

    def __init__(self, state: list[dict] = [], new_data: list[dict] = [], attention: Literal["full", "simple", "none"] = "full"):
        super().__init__(state, new_data, attention)

    def fetch(self) -> list[dict]:
        """
        Consume new_data and extend state with new data.
        Simple and full attention return all for this source.
        Return [] if not connected
        """
        if self.attention == "none" or not self.connected:
            return []
        
        new_data = self.new_data.copy()
        self.state.extend(new_data)
        self.new_data = []
    
        return new_data


    def add_data(self, data: list[dict]) -> None:
        """Add new data to the source if connected and attention is not none. This method is called by the parent GradioUI class when new data is received from the UI"""
        if self.connected and self.attention != "none":
            self.new_data.extend(deepcopy(data))

    def has_new(self) -> bool:
        """
        Indicate if there is new data in state that has not been consumed yet.

        The implementation must return True if:
        - There is new_data is not empty
        - self.attention is not none
        """
        return bool(self.new_data) and self.attention != "none" and self.connected

class InputSourceHub:
    """A list of input sources for the agent to fetch input from. Contains methods to modify attentions and to fetch data from all chosen sources"""

    sources: dict[str, InputSource]
    """A dict mapping source name to InputSource object"""

    def __init__(self, sources: dict[str, InputSource] = {}):
        """Initialize the object"""
        self.sources = copy(sources)

    def connect_all(self) -> None:
        """Connect to all sources"""
        for k, v in self.sources.items():
            v.connect()

    def get_connected_statuses(self) -> dict[str, bool]:
        """Return the connected statuses of all sources"""
        connected_statuses = {}
        for name, source in self.sources.items():
            connected_statuses[name] = source.connected
        return connected_statuses


    def change_attention(self, source_name: str, attention: Literal["full", "simple", "none"]) -> None:
        """Change the attention of a specific input source"""
        if source_name not in self.sources:
            raise ValueError(f"Source {source_name} not found in sources")

        if attention not in ["full", "simple", "none"]:
            raise ValueError(f"Invalid attention")
        self.sources[source_name].attention = attention

    def get_attentions(self) -> dict[str, str]:
        """Get the attentions of all sources"""
        attentions = {}
        for name, source in self.sources.items():
            attentions[name] = source.attention
        return attentions

    def fetch(self) -> None:
        """Fetch new data from all connected input sources whose attention is not none """
        new_messages = []
        for k, v in self.sources.items():
            if v.attention != "none" and v.connected:
                new_messages.extend(v.fetch())
        return new_messages

    def has_new(self) -> bool:
        """Check if any source has new data to consume"""
        for name, source in self.sources.items():
            if source.has_new():
                return True
        return False



class OutputSource(ABC):
    """Base class for an output source for the agent to send output to. Contains method to send data and connect to the output source"""

    state: object
    """Contains all the output data from the source for audit"""
    in_use: bool
    """Indicate if the output source is in use by the agent"""
    connected: bool
    """Check if the input source is being connected to be used or not"""

    def __init__(self, in_use: bool = True, state: object = None):
        """Initialize the object"""
        self.in_use = in_use
        self.state = deepcopy(state)
        self.connected = False

    @abstractmethod
    def send_messages(self, messages: list[dict]) -> None:
        """
        Send messages to the output source if the source is connected and in use.

        Input:
            messages: a list of dict in ResponseAPI format received from the agent
        """
        pass

    @abstractmethod
    def send_phrase(self, phrase: str) -> None:
        """
        Send a phrase from the agent to the output source if the source is connected and in use. For streaming purpose, each phrase is a part of a complete response so that the UI can update the latest AI message in real time.
        Once the end of a response is reached, the agent will send a special phrase "||END_OF_RESPONSE||" to notify and the UI can handle it accordingly.
        """
        pass

    @abstractmethod
    def fetch(self) -> list[str]:
        """
        For the source to consume new phrases or messages and extend state with the new data.
        """
        pass

    def connect(self) -> None:
        """Connect to the output source"""
        self.connected = True

class StreamingOutputSource(OutputSource):
    """
    Base class for output source that consume agent phrases gradually for streaming

    Characteristics:
        Has attribute agent_state which is a a list of phrases from agent. state is also such a list.
        connect() doesn't do anything, just set connected to True as default
        send_messages() doesn't do anything.
    """

    state: list[str]
    """Contains all phrases from the agent for audit"""
    new_agent_phrases: list[str]
    """
    Contains all the unconsumed phrases from the agent for the GradioUI to poll and update the ui messages
    For streaming purpose, each phrase is a part of a complete response so that the UI can update the latest AI message in real time.
    Once the end of a response is reached, the agent will send a special phrase "||END_OF_RESPONSE||" to notify and the UI can handle it accordingly.
    """

    def __init__(self, in_use: bool = True, state: list[str] = [], new_agent_phrases: list[str] = []):
        super().__init__(in_use, state)
        self.new_agent_phrases = deepcopy(new_agent_phrases)

    def send_messages(self, messages: list[dict]) -> None:
        """
        Do nothing. Use send_phrase for streaming instead
        """
        return

    def send_phrase(self, phrase: str) -> None:
        """
        Send a phrase from the agent to the output source if the source is connected and in use. For Gradio, this is not needed. The parent GradioUI class will directly send data to the UI
        """
        if self.connected and self.in_use:
            self.new_agent_phrases.append(phrase)


    def fetch(self) -> list[str]:
        """
        For the source to consume new_agent_phrases and extend state with new phrases.
        """
        new_phrases = self.new_agent_phrases.copy()
        self.state.extend(new_phrases)
        self.new_agent_phrases = []
        return new_phrases

class OutputSourceHub:
    """A list of output sources for the agent to send output to. Contains methods to choose which sources are in use and send data to all chosen sources"""

    sources: dict[str, OutputSource]
    """A dict mapping source name to OutputSource object"""

    def __init__(self, sources: dict[str, OutputSource] = {}):
        """Initialize the object"""
        self.sources = copy(sources)

    def connect_all(self):
        """Connect to all sources"""
        for k, v in self.sources.items():
            v.connect()

    def send_messages(self, messages: list[dict]) -> None:
        """Send a list of messages to all output sources that are in use"""
        messages = deepcopy(messages)
        for k, v in self.sources.items():
            if v.in_use:
                v.send_messages(messages)

    def send_phrase(self, phrase: str) -> None:
        """Send a phrase to all output sources that are in use for streaming purpose"""
        for k, v in self.sources.items():
            if v.in_use:
                v.send_phrase(phrase)

    def change_in_use(self, source_name: str, in_use: bool) -> None:
        """Change the in_use of a specific output source"""
        if source_name not in self.sources:
            raise ValueError(f"Source {source_name} not found in sources")
        self.sources[source_name].in_use = in_use



class GradioUI:
    """A gradio chat UI and contain an InputSource and OutputSource connected to it"""
    messages: list[dict]
    """A list of message in ResponseAPI format to be displayed in the Gradio chat UI"""

    input_source: MessageInputSource
    output_source: StreamingOutputSource

    def __init__(self):
        self.messages = []
        self.input_source = MessageInputSource()
        self.output_source = StreamingOutputSource()
        self.input_source.connect()
        self.output_source.connect()
        asyncio.gather(self.start())

    async def start(self) -> None:
        """Start the Gradio UI"""
        def send_user_message(user_input):
            """
            Add user message to the messages list and the input source
            Return the updated messages list
            """
            # The last message can be an empty assistant message. In that case, we need to remove it before adding the user message.
            if len(self.messages) > 0 and self.messages[-1]["role"] == "assistant" and self.messages[-1]["content"] == "":
                self.messages.pop()
            self.messages.append({"role": "user", "content": user_input})
            self.input_source.add_data([{"role": "user", "content": user_input}])
            return "", self.messages


        def fetch():
            """
            Fetch new phrases from the output source and update the messages list
            Return the updated messages list
            """
            new_phrases = self.output_source.fetch()
            response = []
            for phrase in new_phrases:
                # If there's at least 1 message and the last message is from the assistant
                if len(self.messages) > 0 and self.messages[-1]["role"] == "assistant":
                    # If the current phrase is the end of response, we need to append the response to the last message and add a new assistant message
                    if phrase == "||END_OF_RESPONSE||":
                        self.messages[-1]["content"] += "".join(response)
                        response = []
                        self.messages.append({"role": "assistant", "content": ""})
                    # Else we need to append the phrase to the response list and update the last message content when the loop is done
                    else:
                        response.append(phrase)
                # If there's no message or the last message is from the user, we need to add a new assistant message
                else:
                    if phrase == "||END_OF_RESPONSE||":
                        self.messages.append({"role": "assistant", "content": ""})
                    else:
                        self.messages.append({"role": "assistant", "content": phrase})

            # If there's still response left, we need to append it to the last message content
            if len(response) > 0:
                if len(self.messages) > 0 and self.messages[-1]["role"] == "assistant":
                    self.messages[-1]["content"] += "".join(response)
                else:
                    self.messages.append({"role": "assistant", "content": "".join(response)})


            return self.messages
        


        # Define the UI
        with gr.Blocks() as demo:
            gr.Markdown("Work Assistant")
            chatbot = gr.Chatbot(height=500)
            msg = gr.Textbox(label="You")
            send = gr.Button("Send")
            timer = gr.Timer(value=0.5, active=True)

            timer.tick(fn=fetch, inputs=[], outputs=[chatbot])

            send.click(
                send_user_message,
                inputs=[msg],
                outputs=[msg, chatbot]
            )

        demo.launch(prevent_thread_lock=True)
