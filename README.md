# SAP Copilot AI

An AI-powered assistant for the SAP project lifecycle: generate and explain ABAP, convert FS to TS, analyze errors, explain business processes, and prepare for interviews.

**Status: Phases 1-5 working locally** - login + chat with a LangGraph router (ABAP / Functional / Learning agents), Markdown UI, a searchable SAP knowledge base (hybrid vector + keyword search) the agents cite, an abaplint syntax-check loop, a SAP metadata catalog that grounds and checks BAPI/table/field names, and an interview coach.

## Project structure

```
sap-copilot-ai/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app
│   │   ├── config.py          settings from .env
│   │   ├── database.py        SQLAlchemy engine/session
│   │   ├── models.py          User, ChatMessage tables
│   │   ├── schemas.py         request/response models
│   │   ├── security.py        bcrypt + JWT
│   │   ├── deps.py            get_current_user
│   │   ├── routers/           auth.py, chat.py
│   │   └── agents/            LangGraph: router_agent.py, graph.py, llm.py
│   ├── tests/test_api.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                  React + Vite
├── knowledge_base/            (Phase 2) SAP documents and code samples
├── evals/                     (Phase 9) golden test prompts
├── docker-compose.yml         Postgres + backend
└── .env.example
```

## Run locally (without Docker)

### 1. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env            # then edit backend/.env (see below)
uvicorn app.main:app --reload --port 8001
```
Always start the server from inside `backend/`, because the app reads `backend/.env`.

Open http://localhost:8001/docs to try the API.

### 2. Frontend
```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```
Open http://localhost:5173, create an account and start chatting.

### 3. Tests
```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

## Run with Docker (Postgres + backend)
```bash
cp .env.example .env     # set JWT_SECRET and optionally GROQ_API_KEY
docker compose up --build
```

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite for local, PostgreSQL for docker / Neon |
| `JWT_SECRET` | Long random string: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GROQ_API_KEY` | Optional in Phase 1. Without it the router uses keyword rules and agents return placeholder answers |

**Never commit `.env`.** It is already in `.gitignore`. If a key was ever pasted in a chat or committed, rotate it.

## API endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | no | health check |
| POST | `/auth/register` | no | create account |
| POST | `/auth/login` | no | returns JWT (form fields `username` = email, `password`) |
| GET | `/auth/me` | yes | current user |
| POST | `/chat` | yes | `{"message": "..."}` -> `{"agent", "answer"}` |
| GET | `/chat/history` | yes | recent messages |

## Roadmap

1. Foundation - done
2. Knowledge base + RAG (code-aware chunking, metadata, hybrid search) - done
3. SAP metadata catalog (YAML, with honest verified / documented / unverified status) - done
4. abaplint syntax-check loop - done
5. Interview coach (question bank, key-point scoring, progress) - done
6. FS -> TS document intelligence - planned
7. Error analyzer (ST22 / error messages) - planned
8. Roadmaps, analytics dashboard - planned
9. Evaluation and deployment - planned

## Phase 2: knowledge base

```
knowledge_base/
├── raw/        downloaded sample repos (git-ignored; created by scripts/fetch_sources.sh)
├── notes/      YOUR notes in Markdown (see notes/README.md)
└── chroma/     the vector database (git-ignored, created by the ingest command)
evals/retrieval_cases.json   test questions with expected answers
backend/app/rag/             chunker.py, embedder.py, store.py, retriever.py, ingest.py, cli.py
```

Commands (run from `backend/` with the virtual environment active):

```bash
pip install -r requirements.txt                       # adds fastembed, chromadb, rank-bm25
bash ../scripts/fetch_sources.sh                      # download sample repos (once)
python -m app.rag.cli ingest ../knowledge_base/raw/abap-cheat-sheets --source abap-cheat-sheets
python -m app.rag.cli ingest ../knowledge_base/raw/cloud-abap-rap --source cloud-abap-rap
python -m app.rag.cli stats                           # what is stored
python -m app.rag.cli search "read a single row from an internal table" -k 5
python -m app.rag.cli eval ../evals/retrieval_cases.json            # quality check (hybrid)
python -m app.rag.cli eval ../evals/retrieval_cases.json --mode bm25    # compare keyword-only
```

The first ingest downloads the embedding model (BAAI/bge-small-en-v1.5, ~130 MB) once.

Environment variables (optional): `KB_DIR` (default `../knowledge_base`), `EMBEDDING_BACKEND` (`fastembed`, or `hash` for offline tests), `EMBEDDING_MODEL`.

New endpoint: `GET /kb/search?q=...&k=5&mode=hybrid|vector|bm25&module=MM&technology=rap&object_type=method&source=...` (login required).

### Agents use the knowledge base

The `abap` and `learning` agents retrieve the top 4 excerpts (hybrid search) and give them to the LLM with instructions to cite `[1]`, `[2]` only when they help and to say so when the knowledge base does not cover the question. The answer ends with a **Knowledge base sources cited** list (only the excerpts the answer actually cites; if none were used it says so). If the knowledge base is empty or cannot load, chat works exactly as before. Set `RAG_ENABLED=false` in `backend/.env` to switch it off. The first chat after a server start takes a few extra seconds while the embedding model loads.

## Phase 4: syntax check with abaplint

The ABAP agent now checks the code it writes with [abaplint](https://abaplint.org) (open source, no SAP system needed). If problems are found, the LLM gets the exact lines and messages and corrects its answer (up to `ABAPLINT_MAX_FIXES`, default 2). The answer ends with a status note: passed, or the issues that remain.

One-time install (needs Node.js):

```bash
cd backend/tools/abaplint
npm install
```

What it checks: ABAP grammar (`parser_error`) and, in complete programs/classes, declarations (`check_syntax`), for example `DATA(x) TYPE ...`, inline declarations in `CHANGING`, undeclared variables. What it cannot check: whether a BAPI, table, class or field exists in your system (abaplint has no data dictionary, so "not found" messages for SAP objects are ignored on purpose). That is the job of the Phase 3 metadata catalog.

If abaplint is not installed the chat works as before without the note. Settings in `backend/.env`: `ABAPLINT_ENABLED=false` to switch off, `ABAPLINT_BIN` to point at another abaplint, `ABAPLINT_MAX_FIXES`.

## Phase 3: SAP catalog

`knowledge_base/catalog/*.yaml` describes SAP objects the copilot should get exactly right: function modules / BAPIs (with parameters and direction), structures, tables and table types.

- **Before answering**, the ABAP agent puts the catalog facts for the objects named in the question in front of the LLM.
- **After answering**, `backend/app/catalog/` scans the generated ABAP (`CALL FUNCTION` parameters and sections, `ls_x-field` components, `SELECT` field lists) and compares them with the catalog. A definite conflict (for example a parameter in the wrong section, or a field that does not exist in a structure whose list is marked `complete`) makes the agent ask the LLM for one correction round. Names the catalog does not know are only reported as "not confirmed", never called wrong.
- The answer ends with a **SAP catalog check** note listing what was found, conflicts and unknowns, with each entry's status.

**Honesty about the data:** the shipped entries are seed data written from general knowledge and are all `status: unverified`. Nothing is marked `verified` until someone checks it in SE37 / SE11 or official documentation and records the `source`. See `knowledge_base/catalog/README.md`.

```bash
cd backend
python -m app.catalog.cli validate
python -m app.catalog.cli show BAPI_PR_CREATE
python -m app.catalog.cli check some_code.abap
```

Endpoints (login required): `GET /catalog/stats`, `GET /catalog/search?q=...`, `GET /catalog/{name}`. Switch off with `CATALOG_ENABLED=false`.

## Phase 5: Interview coach

The **Interview coach** tab asks ABAP interview questions (`knowledge_base/interview/*.yaml`), scores your answer and tracks progress per topic.

Score (0-10) = share of the question's expected key points your answer covers: keyword matching first, then an AI check of the points that were missed (it can accept the same idea in other words). Without an LLM key only keywords are used. This measures coverage of expected points, not overall answer quality, and the UI says so. The question bank was written from general ABAP knowledge and is not reviewed against SAP documentation; review it and add your own questions in your own words.

Endpoints (login required): `GET /interview/topics`, `POST /interview/question`, `POST /interview/answer`, `GET /interview/progress`.

```bash
cd backend
python -m app.interview.cli validate
python -m app.interview.cli list
```

## Security notes

- Secrets live only in `backend/.env` (git-ignored). `.env.example` must contain placeholders only.
- Never put keys in the frontend (`VITE_*` values are public).
- Do not put employer or client code, specifications or data in `knowledge_base/` (notes, catalog, interview questions).
- If a key was ever pasted somewhere public, rotate it.


## Phase 6: Error analyzer

Paste an ST22 short dump or an SAP error message in the "Error analyzer" tab. The backend (1) parses the facts that
are literally in the text (runtime error, exception, program, line, message class/number), (2) matches them against
`knowledge_base/errors/*.yaml` (causes, fix steps, transactions to check; every entry has a status, shipped ones are
`unverified`), and (3) asks the LLM for an explanation based only on those facts. Without an LLM key you still get
(1) and (2). Limits: the explanation can be wrong, and the knowledge entries are general SAP knowledge that you
should review. Do not paste confidential customer data.
