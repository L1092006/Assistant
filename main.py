from assistant import Assistant
import asyncio

async def main():
    assistant = Assistant(reasoning="none")
    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
