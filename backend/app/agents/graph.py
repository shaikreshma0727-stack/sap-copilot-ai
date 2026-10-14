"""LangGraph workflow for Phase 1:

    router -> (abap | functional | learning) -> END

The specialist agents are placeholders for now: they call the LLM with a role
prompt if a key is configured, otherwise they return a stub message. In later
phases they get tools (RAG search, BAPI catalog lookup, abaplint)."""

from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.agents.catalog_check import catalog_context, catalog_fix, catalog_note
from app.agents.code_check import check_and_fix
from app.agents.llm import ask_llm
from app.agents.rag_context import build_prompt, retrieve, sources_footer
from app.agents.router_agent import route
from app.agents.state import AgentState

SYSTEM_PROMPTS = {
    "abap": (
        "You are a senior SAP ABAP developer assisting other SAP developers. "
        "Give accurate, modern ABAP (7.4+ syntax where suitable). If you are not sure a BAPI, "
        "table or field exists, say so clearly instead of guessing; never invent BAPI parameters, "
        "structure names or field names. Inline declarations are written DATA(var) = expr or "
        "INTO @DATA(var), never DATA(var) TYPE ... . Explain your steps."
    ),
    "functional": (
        "You are a senior SAP functional consultant. Explain business processes, configuration "
        "and requirements clearly, naming relevant SAP modules, transactions and tables. "
        "If unsure of an exact detail, say so."
    ),
    "learning": (
        "You are a friendly SAP trainer. Explain concepts step by step for the learner's level, "
        "with simple examples, and offer practice questions where helpful."
    ),
}


def router_node(state: AgentState) -> AgentState:
    return {"agent": route(state["message"])}


# The knowledge base is ABAP/RAP-centric, so only these agents search it.
RAG_AGENTS = {"abap", "learning"}


def _make_agent_node(name: str):
    def node(state: AgentState) -> AgentState:
        question = state["message"]
        hits = retrieve(question) if name in RAG_AGENTS else []
        prompt = build_prompt(question, hits)
        if name == "abap":
            prompt = catalog_context(question) + prompt  # facts about the SAP objects named in the question
        answer = ask_llm(SYSTEM_PROMPTS[name], prompt)
        if answer is None:
            answer = (
                f"[{name} agent] No LLM key configured yet (or the call failed), so this is a "
                f"placeholder. Your message was routed to the '{name}' agent successfully."
            )
        else:
            check_note = catalog_note_text = ""
            if name == "abap":
                ask = lambda system, message: ask_llm(system, message)  # noqa: E731
                for _ in range(2):  # a fix for one checker can undo the other, so alternate (max 2 rounds)
                    before = answer
                    fixed = catalog_fix(question, answer, ask, SYSTEM_PROMPTS[name])
                    answer, check_note = check_and_fix(question, fixed, ask, SYSTEM_PROMPTS[name])
                    if fixed == before:  # the catalog had nothing to correct
                        break
                catalog_note_text = catalog_note(answer)
            answer += sources_footer(hits, answer) + check_note + catalog_note_text
        return {"answer": answer}

    return node


def _pick_agent(state: AgentState) -> str:
    return state["agent"]


@lru_cache
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    for name in ("abap", "functional", "learning"):
        graph.add_node(name, _make_agent_node(name))
        graph.add_edge(name, END)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        _pick_agent,
        {"abap": "abap", "functional": "functional", "learning": "learning"},
    )
    return graph.compile()


def run_copilot(message: str) -> dict:
    result = build_graph().invoke({"message": message})
    return {"agent": result["agent"], "answer": result["answer"]}
