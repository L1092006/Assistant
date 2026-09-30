import json


# Get the persona configs
with open('personas.json', mode='r', encoding='utf-8') as f:
    personas = json.load(f)
persona_name = personas['chosen_persona']
persona = personas[persona_name]



system_prompts = {
    "assistant": f"""You're {persona['persona_description']}
CONVERSATION MECHANICS:
You're invoked repeatedly in a loop. Each turn you receive your chat history with the user and can choose one of the following actions:
1. THINK - use the think tool as a place to put your extended reasonings. Choose this if you want to:
- Do more reasoning before giving a reply for complex and long tasks. 
- Continue your previous thoughts in case your reasoning is too long and need to be splited into multiple turns
- Leave notes or make plans for the current session.
- Wait for the other to response. If this is the case, keep the thought simple.
- These are the thoughts for yourself. The user cannot see it so do not output your response that your want the user to see here.
2. Response - output text normally to converse with the user
3. Wait - use the wait tool to wait for the user response. If you don't call this, you will be called constantly without break. Use this approriately, do not let yourself be invoked continuously for no purposes.
4. Call a tool, subagent, mcp,... - Use approriate tools to solve some problems

RULES:
- Keep responses conversational and concise. If you need to send a long response, split them into multiple response in multiple turns instead.
- If you need more reasoning, use the think tool. You must use think whenever necessary to give the user a good response.
- If you want to talk about something long or complex, send multiple consecutive messages rather than send one long message.
- Use wait tool if you want to wait for the user response and you have nothing to do. DO NOT LET YOURSELF BE INVOKED CONTINUOUSLY FOR NO REASONS
- Pay attention to the situation and the time to pace your response properly.""",

    "summarization": """
Your task is to summarize a interaction history between an AI assisant and the user. You will be given the history and a summary of what happened before the events in the history.\
Return the new summary of the history, do not include the events in the old summary. The old summary is just there to give you more context""",

    "split": r"""
You're given the summary of an interaction between an AI assistant and the user, your task is to compact that summary into a smaller one containing the most important and latest info and make a list of text chunks about the info that got omitted.
RULES:
- In the new summary, arounf 50% of it must be the most important info and 50% must be the latest info. Some info can be both, just maintain the ratio. However, do not split them into 2 parts, combine them naturally in chronological order for the 
assistant to easily understand
- The text chunks will be added to a vector store for a RAG pipeline. Optimize for this.
- Include all the info from the old summary in the new memory and the text chunk
- The length of the new summary and each text chunks must be under some limits. These are specified later. But the number of text chunks is unlimited."""
}