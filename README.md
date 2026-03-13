# Catalyst

Catalyst is an AI-driven SDLC platform.

## Current module

Catalyst currently includes the Backlog Generation module.

This module provides:

- Jira issue context retrieval
- AI-assisted responses from Jira issue data
- Jira epic generation from prompt and optional supporting files
- Jira story generation from generated epic JSON
- Jira-to-Postgres batch ingestion using SQLAlchemy ORM

## Environment variables

Set the following environment variables:

- `JIRA_BASE_URL` (example: `https://your-domain.atlassian.net`)
- `JIRA_USERNAME` (your Jira/Atlassian email)
- `JIRA_AUTH_TOKEN` (Atlassian API token)
- `GROQ_API_KEY`
- `GROQ_MODEL` (optional, default: `llama-3.1-8b-instant`)
- `HUGGINGFACE_EMBEDDING_MODEL` (optional, default: `sentence-transformers/all-MiniLM-L6-v2`)
- `JIRA_FETCH_ISSUES_JQL` (optional, default: `project=TEST AND created>=-365d ORDER BY created DESC`)
- `JIRA_BATCH_SIZE` (optional, default: `50`, max: `100`)
- `JIRA_BATCHES_TO_BE_PROCESSED_COUNT` (optional, default: `10`)
- `POSTGRES_DSN` (example: `postgresql://user:password@localhost:5432/dbname`)
- `ORM_ECHO_SQL` (optional: `false`, `true`, or `debug`)

## Agent API

`/agent` runs a LangGraph flow that fetches a Jira issue and answers using issue context.

Example request:

```json
{
  "message": "What is the current status and summary?",
  "issue_id": "TEST-5"
}
```

## Jira Epic Generation API

`/jira/epic` generates a list of Jira epic JSON objects from a prompt and optional supporting files.

Request format: `multipart/form-data`

- `prompt` (required): text field
- `epic_count` (optional): number of epics to generate (default `3`, range `1` to `10`)
- `supporting_documents` (optional): one or more uploaded files

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
      "epic_summary": "...",
      "business_value": "...",
      "scope": ["..."],
      "out_of_scope": ["..."],
      "assumptions": ["..."],
      "acceptance_criteria": ["..."],
      "risks_and_dependencies": ["..."]
    }
  ]
}
```

Implementation notes:

- Uses LangChain structured output for deterministic JSON schema
- Converts uploaded files into embeddings using HuggingFace embeddings
- Retrieves relevant chunks and passes them as context to epic generation
- If no files are provided, generation proceeds with prompt-only input

## Jira Story Generation API

`/jira/stories` generates child stories from one selected epic JSON returned by `/jira/epic`.

Request format: `application/json`

Example request:

```json
{
  "epic": {
    "epic_id": "EPIC-CUSTOMER-SUCCESS-7AF1D2",
    "epic_name": "Customer Success Self-Serve Analytics Dashboard",
    "epic_summary": "...",
    "business_value": "...",
    "scope": ["..."],
    "out_of_scope": ["..."],
    "assumptions": ["..."],
    "acceptance_criteria": ["..."],
    "risks_and_dependencies": ["..."]
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
        "title": "...",
        "summary": "...",
        "description": "...",
        "acceptance_criteria": ["..."],
        "priority": "Medium"
      }
    ]
  }
}
```

## Streamlit UI

A simple Streamlit UI is available at `ui/app.py`.

Run:

```bash
uv run streamlit run ui/app.py
```

## Jira batch ingestion

Run:

```bash
uv run python -m backlog_generation.data_ingestion_pipeline
```
