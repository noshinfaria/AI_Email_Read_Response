from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from dotenv import load_dotenv
import os
import asyncio

# Load environment variables
load_dotenv()

async def generate_ai_reply(email_body: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    def sync_generate():
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
        prompt = (
            f"You are an email assistant. Please write a polite and professional reply to this email:\n\n"
            f"{email_body}\n\n"
            f"Reply:"
        )
        response = llm([HumanMessage(content=prompt)])
        return response.content

    return await asyncio.to_thread(sync_generate)
