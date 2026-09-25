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
    A client to connect to a SQL database.

    Serve as an abtraction from the specific SQL database so that we can switch between different versions.
    """
    @abstractmethod
    def __init__(self) -> None:
        """
        Save all the connection info to attributes
        """
        pass

    @abstractmethod
    def create_agent(self, name: str = None, type: str = None, system_message: str = None) -> None:
        "Add a new agent to agents table"
        pass

    @abstractmethod
    def save_messages(self, messages: list[dict], agent_name: str) -> None:
        """
        Save all the messages 

        For each message, specify the type and the agent who made it in the corresponding columns
        Save the time in UTC

        Parameters:
            messages
        """
        pass

    @abstractmethod
    def get_messages(self, agent_name: str, seconds: int = 60*60*24) -> list[dict]:
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


    def __init__(self, file_path: str = None) -> None:
        """
        Save all the connection info to attributes
        
        If file_path is None, read from .env
        If database is None, create a database with that name
        """
        if file_path is None:
            file_path = os.getenv(DB_NAME, "assistant.db")
        self.file_path = file_path

        # Init the db if needed
        con = sqlite3.connect(self.file_path)
        with con.cursor() as cur:
            # Read the init sql file
            with open("sqlite_init.sql", mode="r", encoding="utf-8") as f:
                statements = f.read()

            # Exucute the statements
            cur.execute(statements)
        



    def save_messages(self, messages: list[dict], agent_name: str) -> None:
        """
        Save all the messages 
        
        For each message, specify the type and the agent who made it in the corresponding columns
        Save the time in UTC

        Parameters:
            messages
        """
        con = sqlite3.connect(self.file_path)
        with con.cursor() as cur:
            # Get the agent id
            query = "SELECT agent_id FROM agents WHERE name = ?"
            res = cur.execute(query, (agent_name,))
            res = res.fetchone()
            # If the agent doesn't exists, raise an exception
            if res is None:
                raise ValueError(f"No agent with the name {agent_name}")
            agent_id = res[0]

            # Reformat the messages into data to insert
            data = []
            for message in messages:
                raw_string = json.dumps(message)
                # Use the current time in UTC as time
                time = datetime.now(timezone.utc).isoformat()
                message_type = message.get("type", "message")
                data.append((raw_string, time, message_type, agent_id))

            insert_statement = "INSERT INTO messages VALUES (?, ?, ?, ?)"
            cur.executemany(insert_statement, data)

        con.commit()
        con.close()

    def get_messages(self, agent_name: str, seconds: int = 60*60*24) -> list[dict]:
        """
        Get all messages associated with the specify agent in the last specified seconds.
        """
        con = sqlite3.connect(self.file_path)
        with con.cursor() as cur:
            # Get the agent id
            query = "SELECT agent_id FROM agents WHERE name = ?"
            res = cur.execute(query, (agent_name,))
            res = res.fetchone()
            # If the agent doesn't exists, raise an exception
            if res is None:
                raise ValueError(f"No agent with the name {agent_name}")
            agent_id = res[0]

            # Get the messages
            # Get the datetime n seconds ago
            start_time = (datetime.now() - timedelta(seconds=seconds)).isoformat()
            query = "SELECT raw_string FROM messages WHERE agent_id = ? AND datetime >= ?"
            res = cur.execute(query, (agent_id, start_time))
            messages = [json.loads(m[0]) for m in res.fetchall()]
        con.close()
        return messages

    def create_agent(self, name: str = None, type: str = None, system_message: str = None) -> None:
        "Add a new agent to agents table"
        con = sqlite3.connect(self.file_path)
        with con.cursor() as cur:
            insert_statement = "INSERT INTO agents VALUES (?, ?, ?)"
            cur.execute(insert_statement, (name, system_message, type))
        con.commit()
        con.close()


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

