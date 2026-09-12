from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
import json
import uuid
from dotenv import load_dotenv

from openai import AsyncOpenAI
from agents import Agent, Runner, trace, function_tool, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field

load_dotenv(override=True)

with open('personas.json', mode='r', encoding='utf-8') as f:
    personas = json.load(f)
    persona_name = personas['chosen_persona']

# Connect to Chroma and handle add, searches,...
class MemoryClient:
    chroma_client = None
    chroma_collection = None
    embedding_model = None

    # FIXME: change default parameters for production. Get the values from a config file
    def __init__(self, path='./memory/test', collection_name='test', override_collection=True, embedding_model_name='jinaai/jina-embeddings-v5-text-small'):
        self.chroma_client = PersistentClient(path=path)
        
        # Delete the collection if override_collection = True
        if override_collection and collection_name in [c.name for c in self.chroma_client.list_collections()]:
            self.chroma_client.delete_collection(collection_name)
        
        self.chroma_collection = self.chroma_client.get_or_create_collection(collection_name)

        self.embedding_model = SentenceTransformer(embedding_model_name, trust_remote_code=True)


    # BASIC FUNCTIONALITIES (ADD/SEARCHES)
    # Add documents to the collection
    def add(self, chunks: list[dict]):
        """
        IN:
            chunks: a list of dict. Each dict contains:
            {
                'document': The string document,
                'metadata': The dict of metadata
            }
        """
        documents = [c['document'] for c in chunks]
        metadatas = [c['metadata'] for c in chunks]
        embeddings = self.embedding_model.encode(
            documents,
            task='retrieval',
            prompt_name='document'
        )

        self.chroma_collection.add(
            ids=[str(uuid.uuid4()) for _ in range(len(chunks))],
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
    

    # Simple similarity search
    def simple_search(self, queries: list[str], n_results=5):
        """
        IN:
            queries: A list of string queries
            n_results: The number of chunks returned for each query

        OUT:
            A list of lists.
            Each list contains results of a query. Each result:
            {
                'document': The string document,
                'metadata': The dict of metadata
            }
        """
        embeddings = self.embedding_model.encode(
            queries,
            task='retrieval',
            prompt_name='query'
        )

        results = self.chroma_collection.query(
            query_embeddings=embeddings,
            n_results=n_results
        )

        extracted_results = []

        for i in range(len(queries)):
            chunks = []
            for c in zip(results['documents'][i], results['metadatas'][i]):
                chunks.append({
                    'document': c[0],
                    'metadata': c[1]
                })
            extracted_results.append(chunks)

        return extracted_results
    

# Store, update, provide memories for the current session
class Memory:
    # The number of current memories (old+new) 
    num_memories = 0
    # The most recent memories returned by the latest search. Around 20% of the current memories
    new_memories = []
    # The older memories maintained and updated by the maintenance agent. Around 80% of the current memories
    old_memories = []
    # All memories in this session 
    all_memories = []

    # Maintenance agent which updates and removes approriate old memories. Always run
    maintenance_agent = None
    # The number of seconds between each invocation of maintenance agent
    unit_time = 0
    
    # MemoryClient object
    memory_client = None

    def __init__(self, maintenance_model='TBD'):
        self.num_memories = 0
        self.new_memories = []
        self.old_memories = []
        self.all_memories = []


        # Init model objects and agents
        ollama_client = AsyncOpenAI(base_url="http://localhost:11434/v1")
        maintenance_model_obj = OpenAIChatCompletionsModel(model=maintenance_model, openai_client=ollama_client)
        # Init agent with essential tools
        # FIXME: Import system prompt
        self.maintenance_agent = Agent(name="Maintenance Agent", instructions=self.system_prompts.get("maintenance_agent"), model=maintenance_model_obj)
        self.unit_time = 0
        
        # MemoryClient object
        self.memory_client = MemoryClient()


