from typing import TypedDict


class AgentState(TypedDict, total=False):
    message: str  # the user's question
    agent: str  # chosen agent: abap | functional | learning
    answer: str  # final answer
