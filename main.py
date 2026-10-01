from assistant import Assistant
import asyncio
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv(), override=True)

async def main():
    model = os.getenv("MODEL")
    url = os.getenv("PROVIDER_URL")
    api_key = os.getenv("API_KEY")

    assistant = Assistant(model=model, reasoning="none", url=url, api_key=api_key)
    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
