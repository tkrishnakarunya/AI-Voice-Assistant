from llama_index.core.chat_engine import SimpleChatEngine
from src.llm import load_llm
from src.agent import VoiceAssistantAgent

def get_chat_engine():

    llm = load_llm()

    chat_engine = SimpleChatEngine.from_defaults(
        llm=llm,
        system_prompt="You are AIVA (Artificial intelligence voice assistance), a helpful, friendly, and knowledgeable AI voice assistant. Always identify yourself as AIVA if asked about your name, creator, or identity. You must never say you are Qwen or created by Alibaba. You are AIVA."
    )

    return VoiceAssistantAgent(chat_engine)