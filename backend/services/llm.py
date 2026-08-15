from functools import lru_cache
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from backend.config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.llm_model,
        anthropic_api_key=settings.anthropic_api_key,
        max_tokens=settings.llm_max_tokens,
    )


def invoke(user_prompt: str, system_prompt: str = "") -> str:
    llm = get_llm()
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_prompt))
    return llm.invoke(messages).content
