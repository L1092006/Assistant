-- Create the tables


-- All messages from all agents
CREATE TABLE "messages" (
    "id" INTEGER,  
    "raw_string" TEXT NOT NULL,
    "datetime" TEXT DEFAULT CURRENT_TIMESTAMP,
    -- The type of the message (message, function_call,...)
    "type" TEXT NOT NULL,
    "agent_id" INTEGER NOT NULL,
    PRIMARY KEY("id"),
    FOREIGN KEY("agent_id") REFERENCES "agents"("id")
);


-- All agents, including subagents and main assistants with different system message
CREATE TABLE "agents" (
    "id" INTEGER,
    "name" TEXT NOT NULL,
    "system_message" TEXT NOT NULL,
    "type" TEXT NOT NULL CHECK("type" IN ('assistant', 'subagent')),
    PRIMARY KEY("id")
)
