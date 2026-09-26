-- Create the tables


-- All messages from all agents
CREATE TABLE IF NOT EXISTS "messages" (
    "id" INTEGER PRIMARY KEY,  
    "raw_string" TEXT NOT NULL,
    "datetime" TEXT NOT NULL,
    -- The type of the message (message, function_call,...)
    "type" TEXT NOT NULL,
    "agent_id" INTEGER NOT NULL,
    FOREIGN KEY("agent_id") REFERENCES "agents"("id")
);


-- All agents, including subagents and main assistants with different system message
CREATE TABLE IF NOT EXISTS "agents" (
    "id" INTEGER PRIMARY KEY,
    "name" TEXT NOT NULL UNIQUE,
    "system_message" TEXT NOT NULL,
    "type" TEXT NOT NULL CHECK("type" IN ('assistant', 'subagent'))
)
