# Catalyst

Catalyst is an AI-driven SDLC platform. The current repository focuses on backlog generation: generate Jira-ready epics and stories, publish them to Jira in bulk, query Jira issue context, and ingest Jira issue data into Postgres.

## What it does

- Generate epics from a prompt and optional supporting documents
- Generate implementation-ready stories from one selected epic
- Publish generated epics or stories to Jira with Jira bulk issue creation
- Query Jira issue context through a simple agent endpoint
- Ingest Jira issues and relationships into Postgres

## Project layout

```text
main.py                         FastAPI application entrypoint
backlog_generation/epic_agent.py     Epic and story generation models and logic
backlog_generation/simple_langgraph.py  Jira-aware agent flow
backlog_generation/data_ingestion_pipeline.py  Jira to Postgres ingestion
jira_utils.py                   Jira payload mapping and auth helpers
ui/app.py                       Streamlit UI
env.copy                        Environment template
```

## Quick start

1. Create and activate a Python environment.
2. Install dependencies.
3. Copy `env.copy` to `.env` and fill in the required values.
4. Start the API.

Example using `uv`:

```bash
uv sync
cp env.copy .env
fastapi run main.py
```

The API will then be available at `http://127.0.0.1:8000`.

## PRD source priority toggles

For PRD generation requests, you can provide both code and document inputs and control source emphasis using two mutually exclusive flags:

- `prioritize_code`: when `true`, code is high priority and documents are still included as secondary context
- `prioritize_documents`: when `true`, documents are high priority and code is still included as secondary context
- If both are `true`, the API returns `400` (invalid request)
- If neither is selected, the pipeline auto-biases priority based on analyzed code and document content

These priorities are applied through generation, review, and reconciliation stages.

## Required configuration

Core Jira configuration:

- `JIRA_BASE_URL`: Jira site URL, for example `https://your-domain.atlassian.net`
- `JIRA_USERNAME`: Jira or Atlassian account email
- `JIRA_AUTH_TOKEN`: Jira API token
- `JIRA_PROJECT_ID`: Jira project ID used when publishing epics or stories

Generation configuration:

- `GROQ_API_KEY`: required for epic and story generation
- `GROQ_MODEL`: optional, defaults to `openai/gpt-oss-120b` in code
- `HUGGINGFACE_EMBEDDING_MODEL`: optional, defaults to `sentence-transformers/all-MiniLM-L6-v2`

Jira publish configuration:

- `JIRA_BULK_ISSUES_ENDPOINT`: optional override for Jira bulk create endpoint
- `JIRA_DEFAULT_PRIORITY_ID`: optional, defaults to `3`
- `JIRA_DEFAULT_LABELS`: optional comma-separated labels applied to published items
- `JIRA_EPIC_ISSUE_TYPE`: optional, defaults to `Epic`
- `JIRA_EPIC_NAME_FIELD`: optional custom field id for Jira Epic Name, for example `customfield_10011`
- `JIRA_STORY_ISSUE_TYPE`: optional, defaults to `Story`
- `JIRA_STORY_DEFAULT_LABELS`: optional comma-separated labels for published stories
- `JIRA_STORY_PARENT_FIELD`: optional custom field id used to store the parent epic reference
- `JIRA_PRIORITY_HIGHEST_ID`: optional Jira priority id override for `Highest`
- `JIRA_PRIORITY_HIGH_ID`: optional Jira priority id override for `High`
- `JIRA_PRIORITY_MEDIUM_ID`: optional Jira priority id override for `Medium`
- `JIRA_PRIORITY_LOW_ID`: optional Jira priority id override for `Low`
- `JIRA_PRIORITY_LOWEST_ID`: optional Jira priority id override for `Lowest`

Ingestion and database configuration:

- `JIRA_FETCH_ISSUES_JQL`: optional JQL used for batch ingestion
- `JIRA_BATCH_SIZE`: optional, defaults to `50`
- `JIRA_BATCHES_TO_BE_PROCESSED_COUNT`: optional, defaults to `10`
- `POSTGRES_DSN`: Postgres connection string
- `ORM_ECHO_SQL`: optional, `false`, `true`, or `debug`

## Database migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).  
`POSTGRES_DSN` must be set in `.env` (or exported in the shell) before running any migration command.

```bash
set -a 
source .env 
set +a     
```

**Apply all pending migrations (run after first clone or after schema changes):**

```bash
alembic upgrade head
```

**Generate a new migration after changing ORM models:**

```bash
alembic revision --autogenerate -m "describe_your_change"
alembic upgrade head
```

**Roll back the last migration:**

```bash
alembic downgrade -1
```

**Check current migration state:**

```bash
alembic current
alembic history --verbose
```

---

## Inspecting the database

The project connects to PostgreSQL at the DSN defined in `POSTGRES_DSN`.  
Default from `env.copy`: `postgresql://user:password@localhost:5432/aiproductcode`

**If Postgres is running inside a Docker container**, find the container name first:

```bash
docker ps --filter "ancestor=postgres" --format "{{.Names}}"
```

Then open a `psql` session:

```bash
# Replace <container> with your container name (e.g. postgres, catalyst-db, etc.)
docker exec -it <container> psql -U username -d catalyst
```

**Useful psql commands once connected:**

```sql
-- List all tables
\dt

-- Inspect a specific table's columns
\d backlogs
\d generated_epics
\d generated_stories

-- View rows
SELECT id, prompt, status, created_at FROM backlogs ORDER BY created_at DESC LIMIT 10;
SELECT id, epic_name, status, jira_key FROM generated_epics LIMIT 20;
SELECT id, title, status, jira_key FROM generated_stories LIMIT 20;

-- Exit psql
\q
```

**If Postgres is running locally (not in Docker):**

```bash
psql -U user -d aiproductcode
```

---



Run the FastAPI server:

```bash
fastapi run main.py
```

Run the Streamlit UI:

```bash
uv run streamlit run ui/app.py
```

Run Jira batch ingestion:

```bash
uv run python -m backlog_generation.data_ingestion_pipeline
```

## API summary

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/` | `GET` | Health-style greeting endpoint |
| `/agent` | `POST` | Ask a question about a Jira issue |
| `/jira/epic` | `POST` | Generate epics from prompt and files |
| `/jira/stories` | `POST` | Generate stories from one epic |
| `/jira/publish/issues` | `POST` | Publish generated epics or stories to Jira |

## Agent API

`/agent` fetches Jira issue context and answers a question using that context.

Example request:

```json
{
  "message": "What is the current status and summary?",
  "issue_id": "TEST-5"
}
```

## Epic generation

`/jira/epic` generates a list of Jira epic JSON objects from a prompt and optional supporting files.

Request format: `multipart/form-data`

- `prompt`: required text field
- `epic_count`: optional number of epics, default `3`, valid range `1` to `10`
- `supporting_documents`: optional uploaded files

Example request:

```bash
curl -X POST "http://localhost:8000/jira/epic" \
  -F 'prompt=Build a self-serve analytics dashboard for customer success teams.' \
  -F 'epic_count=3' \
  -F 'supporting_documents=@./docs/requirements.txt' \
  -F 'supporting_documents=@./docs/constraints.md'
```

Example response:

```json
{
  "epics": [
    {
      "epic_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2",
      "epic_name": "Customer Success Self-Serve Analytics Dashboard",
      "epic_summary": "Build a dashboard for customer success teams to explore account health and adoption signals.",
      "business_value": "Reduces manual reporting and improves customer success decision making.",
      "scope": ["Dashboard views", "Search and filters"],
      "out_of_scope": ["Data warehouse redesign"],
      "assumptions": ["Source systems already expose the required metrics"],
      "acceptance_criteria": ["Users can load a dashboard for a selected account"],
      "risks_and_dependencies": ["Metric quality depends on upstream system consistency"]
    }
  ]
}
```

## Story generation

`/jira/stories` generates child stories from one selected epic JSON returned by `/jira/epic`.

Request format: `application/json`

Example request:

```json
{
  "epic": {
    "epic_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2",
    "epic_name": "Customer Success Self-Serve Analytics Dashboard",
    "epic_summary": "Build a dashboard for customer success teams to explore account health and adoption signals.",
    "business_value": "Reduces manual reporting and improves customer success decision making.",
    "scope": ["Dashboard views", "Search and filters"],
    "out_of_scope": ["Data warehouse redesign"],
    "assumptions": ["Source systems already expose the required metrics"],
    "acceptance_criteria": ["Users can load a dashboard for a selected account"],
    "risks_and_dependencies": ["Metric quality depends on upstream system consistency"]
  },
  "story_count": 5
}
```

Example response:

```json
{
  "stories": {
    "epic_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2",
    "stories": [
      {
        "story_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2-STORY-01",
        "epic_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2",
        "title": "Implement dashboard summary API",
        "summary": "Create an endpoint that returns account-level summary metrics.",
        "description": "Build the API contract, service layer, and response model for summary metrics.",
        "acceptance_criteria": ["Endpoint returns validated summary metrics"],
        "priority": "Medium"
      }
    ]
  }
}
```

## Jira publish API

`/jira/publish/issues` converts generated output into Jira bulk `issueUpdates` and sends that payload to Jira's `/rest/api/3/issue/bulk` endpoint.

Supported query parameters:

- `type=epic`: default mode, expects payload body `{ "epics": [...] }`
- `type=story`: expects payload body `{ "stories": { "epic_id": "...", "stories": [...] } }`
- `parent-key`: optional for story publish, for example `TEST-25`; when provided, each story is published with `fields.parent.key = TEST-25`

### Publish epics

Example request body:

```json
{
  "epics": [
    {
      "epic_id": "EPIC-DARK-THEME-123ABC",
      "epic_name": "Dark theme implementation",
      "epic_summary": "Implement dark theme support across the application.",
      "business_value": "Improves accessibility and usability in low-light environments.",
      "scope": ["Theme tokens", "Component styling"],
      "out_of_scope": ["Brand redesign"],
      "assumptions": ["Design tokens already exist"],
      "acceptance_criteria": ["Users can enable dark theme across the application"],
      "risks_and_dependencies": ["Legacy components may need additional refactoring"]
    }
  ]
}
```

Example cURL:

```bash
curl -X POST "http://localhost:8000/jira/publish/issues" \
  -H "Content-Type: application/json" \
  -d @generated_epics.json
```

Epic mapping behavior:

- `summary` is mapped from `epic_name`
- `issuetype.name` defaults to `Epic`
- `description` is generated in Atlassian Document Format from epic summary, business value, scope, assumptions, acceptance criteria, and risks
- `project.id` is taken from `JIRA_PROJECT_ID`
- `priority.id` defaults to `3` unless overridden
- `labels` are derived from `JIRA_DEFAULT_LABELS` and the epic name
- `JIRA_EPIC_NAME_FIELD`, when set, receives the epic name

### Publish stories

Example request body:

```json
{
  "stories": {
    "epic_id": "EPIC-SHIPMENT-TRACKING-FEATURE-CF9354",
    "stories": [
      {
        "story_id": "STORY-001",
        "epic_id": "EPIC-SHIPMENT-TRACKING-FEATURE-CF9354",
        "title": "Expose shipment tracking API endpoint",
        "summary": "Create a REST endpoint that returns the current status for a given shipment ID.",
        "description": "Add GET /api/track/{shipmentId} to the backend and return a normalized status object.",
        "acceptance_criteria": [
          "Given a valid shipment ID, the endpoint returns the current status within 2 seconds",
          "If the shipment ID does not exist, the endpoint returns 404"
        ],
        "priority": "High"
      }
    ]
  }
}
```

Example cURL with Jira parent key:

```bash
curl -X POST "http://localhost:8000/jira/publish/issues?type=story&parent-key=TEST-25" \
  -H "Content-Type: application/json" \
  -d @generated_stories.json
```

Story mapping behavior:

- `summary` is mapped from `title`, with fallback to `summary`
- `issuetype.name` defaults to `Story`
- `description` is generated in Atlassian Document Format from story description, story id, parent epic reference, and acceptance criteria
- `project.id` is taken from `JIRA_PROJECT_ID`
- `priority.id` is derived from `priority` using `JIRA_PRIORITY_*_ID`, with fallback to `JIRA_DEFAULT_PRIORITY_ID`
- `labels` are derived from `JIRA_STORY_DEFAULT_LABELS` or `JIRA_DEFAULT_LABELS`
- `fields.parent.key` is set only when `parent-key` is provided
- `JIRA_STORY_PARENT_FIELD`, when set, receives either `parent-key` or the generated story epic reference

Example Jira response:

```json
{
  "issues": [
    {
      "id": "10303",
      "key": "TEST-22",
      "self": "https://your-domain.atlassian.net/rest/api/3/issue/10303"
    }
  ],
  "errors": []
}
```

## Notes and caveats

- The generated `epic_id` in the AI output is an internal identifier, not automatically a Jira issue key.
- For story publishing under an existing Jira epic, prefer `parent-key=YOUR-EPIC-KEY`.
- Some Jira projects require custom fields for Epic Name or parent linkage. Use `JIRA_EPIC_NAME_FIELD` and `JIRA_STORY_PARENT_FIELD` where needed.
- If Jira rejects publish requests, inspect the returned `errors` array or the HTTP error detail from the API.

## Implementation details

- Structured generation uses LangChain and Groq models
- Supporting documents are chunked, embedded, and retrieved for epic generation context
- Jira publish payloads are constructed in `jira_utils.py`
- Jira ingestion persists issues, hierarchy, and issue links into Postgres with SQLAlchemy
