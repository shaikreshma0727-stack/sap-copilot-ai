"""Router Agent: decides which specialist agent should handle a message.

Uses the LLM when available; otherwise (or if the LLM gives an unusable reply)
falls back to simple keyword rules, so routing always works."""

from app.agents.llm import ask_llm

AGENTS = ("abap", "functional", "learning")

ROUTER_PROMPT = """You are a router for an SAP assistant. Classify the user's message into exactly one label:
- abap: writing, explaining, debugging or improving ABAP / CDS / RAP / OData code, SAP errors and dumps, BAPIs, BADIs, exits, tables
- functional: SAP business processes and modules (MM, SD, FI, CO, PP, HCM...), configuration, requirements, FS/TS/BRD documents
- learning: learning SAP concepts, interview questions, certification practice, quizzes, study roadmaps
Reply with ONLY the label, nothing else."""

ABAP_KEYWORDS = (
    "abap", "code", "program", "report", "bapi", "badi", "user exit", "cds", "rap", "odata",
    "alv", "select ", "internal table", "function module", "dump", "st22", "short dump",
    "debug", "error", "class", "method", "smartform", "adobe form", "idoc", "bdc",
)
FUNCTIONAL_KEYWORDS = (
    "business process", "p2p", "procure", "o2c", "order to cash", "purchase", "sales order",
    "configuration", "customizing", "spro", "module", "mm ", "sd ", "fi ", "co ", "pp ",
    "functional", "fs ", "ts ", "brd", "requirement", "specification",
)
LEARNING_KEYWORDS = (
    "learn", "interview", "quiz", "certification", "roadmap", "explain", "what is",
    "difference between", "practice", "beginner", "study", "tutorial", "syllabus",
)


# Clear learning intent: counts extra so "MM interview questions" is not routed to functional.
STRONG_LEARNING_KEYWORDS = ("interview", "quiz", "certification", "roadmap", "practice questions")


def keyword_route(message: str) -> str:
    text = f" {message.lower()} "
    scores = {
        "abap": sum(k in text for k in ABAP_KEYWORDS),
        "functional": sum(k in text for k in FUNCTIONAL_KEYWORDS),
        "learning": sum(k in text for k in LEARNING_KEYWORDS)
        + 2 * sum(k in text for k in STRONG_LEARNING_KEYWORDS),
    }
    best = max(scores, key=scores.get)
    # Nothing matched: a learning-style answer is the safest default.
    return best if scores[best] > 0 else "learning"


def route(message: str) -> str:
    reply = ask_llm(ROUTER_PROMPT, message)
    if reply:
        label = reply.strip().lower().strip(".\"' ")
        if label in AGENTS:
            return label
    return keyword_route(message)
