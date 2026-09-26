import pymysql
from abc import ABC, abstractmethod
import sqlite3
from dotenv import load_dotenv, find_dotenv
import os
import json
from datetime import datetime, timezone, timedelta

# Load env
load_dotenv(find_dotenv())
class SQLClient(ABC):
    """
    A client to connect to a SQL database to read and write messages of a specific agent.

    Serve as an abtraction from the specific SQL database so that we can switch between different versions.
    """

    agent_id: str
    "The agent id"


    @abstractmethod
    def __init__(self, agent_name: str = None, agent_type: str = None, system_message: str = None) -> None:
        """
        Save all the connection info to attributes. Init the db if needed. Save the agent id 

        Parameters:
            agent_name: the name of the agent to get messages from and save messages to. If None, read from the .env
            agent_type: the type of the agent. Needed when the agent doesn't exist in the db
            system_message: the system_message of the agent. Needed when the agent doesn't exist in the db
        """
        pass

    @abstractmethod
    def _create_agent(self, name: str = None, type: str = None, system_message: str = None) -> None:
        "Add a new agent to agents table. Return the agent_id"
        pass


    @abstractmethod
    def save_messages(self, messages: list[dict]) -> None:
        """
        Save all the messages 

        For each message, specify the type and the agent who made it in the corresponding columns
        Save the time in UTC

        Parameters:
            messages
        """
        pass

    @abstractmethod
    def get_messages(self, seconds: int = 60*60*24) -> list[dict]:
        """
        Get all messages associated with the specify agent in the last specified seconds.
        """
        pass

class SQLiteClient(SQLClient):
    """
    A client to connect to a SQL database.

    Serve as an abtraction from the specific SQL database so that we can switch between different versions.
    """
    file_path: str
    agent_id: str

    def __init__(self, file_path: str = None, agent_name: str = None, agent_type: str = None, system_message: str = None) -> None:
        """
        Save all the connection info to attributes. Init the db if needed. Save the agent id 

        Parameters:
            file_path: The path to the db file. If file_path is None, read from .env
            agent_name: the name of the agent to get messages from and save messages to
            agent_type: the type of the agent. Needed when the agent doesn't exist in the db
            system_message: the system_message of the agent. Needed when the agent doesn't exist in the db
        """
        if file_path is None:
            file_path = os.getenv("DB_PATH", "sql_database/assistant.db")
        self.file_path = file_path

        

        # Init the db if needed
        con = sqlite3.connect(self.file_path)
        cur = con.cursor()
        # Read the init sql file
        with open("sql_database/sqlite_init.sql", mode="r", encoding="utf-8") as f:
            statements = f.read()

        # Exucute the init statements
        cur.executescript(statements)

        # Init the agent
        # Raise error if agent_name is None
        if agent_name is None:
            raise ValueError("No agent_name provided")
        # Get the agent id
        query = "SELECT id FROM agents WHERE name = ?"
        res = cur.execute(query, (agent_name,))
        res = res.fetchone()
        # If the agent doesn't exists, try to create it
        if res is None:
            # If not enough agent info is provided, raise an error
            if not agent_type or not system_message:
                raise ValueError(f"The agent {agent_name} doesn't exist yet. Not enough info is provided to insert a new agent record")
            self.agent_id = self._create_agent(name=agent_name, type=agent_type, system_message=system_message)
        else: 
            self.agent_id = res[0]

        cur.close()
        con.commit()
        con.close()
        



    def save_messages(self, messages: list[dict]) -> None:
        """
        Save all the messages 
        
        For each message, specify the type and the agent who made it in the corresponding columns
        Save the time in UTC

        Parameters:
            messages
        """
        con = sqlite3.connect(self.file_path)
        cur = con.cursor()

        # Reformat the messages into data to insert
        data = []
        for message in messages:
            raw_string = json.dumps(message)
            # Use the current time in UTC as time
            time = datetime.now(timezone.utc).isoformat()
            message_type = message.get("type", "message")
            data.append((raw_string, time, message_type, self.agent_id))

        insert_statement = "INSERT INTO messages (raw_string, datetime, type, agent_id) VALUES (?, ?, ?, ?)"
        cur.executemany(insert_statement, data)

        cur.close()
        con.commit()
        con.close()

    def get_messages(self, seconds: int = 60*60*24) -> list[dict]:
        """
        Get all messages associated with the specify agent in the last specified seconds.
        """
        con = sqlite3.connect(self.file_path)
        cur = con.cursor()

        # Get the messages
        # Get the datetime n seconds ago
        start_time = (datetime.now() - timedelta(seconds=seconds)).isoformat()
        query = "SELECT raw_string FROM messages WHERE agent_id = ? AND datetime >= ?"
        res = cur.execute(query, (self.agent_id, start_time))
        messages = [json.loads(m[0]) for m in res.fetchall()]

        cur.close()
        con.close()
        return messages

    def _create_agent(self, name: str = None, type: str = None, system_message: str = None) -> None:
        "Add a new agent to agents table, return the agent id"
        con = sqlite3.connect(self.file_path)
        cur = con.cursor()
        insert_statement = "INSERT INTO agents (name, system_message, type) VALUES (?, ?, ?)"
        cur.execute(insert_statement, (name, system_message, type))
        agent_id = cur.lastrowid
        con.commit()
        con.close()
        return agent_id


class MySQLClient(SQLClient):
    """
    A client to connect to a MySQL database.

    Serve as an abtraction from the specific SQL database so that we can switch between different versions.
    """
    host: str
    user: str
    password: str
    database: str
    port: str


    def __init__(self, host: str = None, user: str = None, password: str = None, database = None) -> None:
        """
        Save all the connection info to attributes
        
        If host is None, read from .env
        """
        pass

