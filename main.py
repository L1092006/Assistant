from assistant import Assistant
import asyncio

async def main():
    assistant = Assistant()
    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
