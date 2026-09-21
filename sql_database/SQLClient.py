import pymysql

class SQLClient:
    """
    A client to connect to a SQL database.

    Serve as an abtraction from the specific SQL database so that we can switch between different versions.
    """
    host: str
    user: str
    password: str
    database: str
    port: str


    def __init__(self, host: str = None, user: str = None, password: str = None, database = None):
        """
        Save all the connection info to attributes
        
        If host is None, read from .env
        If database is None, create a database with that name
        """
        pass

    def save_messages(self, messages: list[dict], agent_name: str):
        """
        Save all the messages 

        For each message, specify the type and the agent who made it in the corresponding columns

        Parameters:
            messages
        """
        pass

    def get_messages(self, agent_name: str, seconds: int = 60*60*24):
        """
        Get all messages associated with the specify agent in the last specified seconds.
        """
        pass