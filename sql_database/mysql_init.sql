-- Create the tables


-- All messages from all agents
CREATE TABLE `messages` (
    `id` INT AUTO_INCREMENT,  
    `raw_string` VARCHAR(512),
    `datetime` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- The type of the message (message, function_call,...)
    `type` VARCHAR(32),
    `agent_id` INT,
    PRIMARY KEY(`id`),
    FOREIGN KEY('agent_id') REFERENCES `agents`(`id`)
);


-- All agents, including subagents and main assistants with different system message
CREATE TABLE `agents` (
    `id` INT AUTO_INCREMENT,
)
