# Catalyst

Catalyst is an **AI-Driven SDLC** platform.

## Current module

Currently, Catalyst includes the **Backlog Generation** module.

This module currently provides:

- Jira issue context retrieval
- AI-assisted responses from Jira issue data
- Jira-to-Postgres batch ingestion for backlog-related issue fields

## Environment variables

Set the following environment variables:

- `JIRA_BASE_URL` (example: `https://your-domain.atlassian.net`)
- `JIRA_USERNAME` (your Jira/Atlassian email)
- `JIRA_AUTH_TOKEN` (Atlassian API token)
- `GROQ_API_KEY`
- `GROQ_MODEL` (optional, default: `llama-3.1-8b-instant`)
- `JIRA_JQL` (optional)
- `JIRA_BATCH_SIZE` (optional, default: `50`, max: `100`)
- `POSTGRES_DSN` (example: `postgresql://user:password@localhost:5432/dbname`)
- `POSTGRES_TABLE` (optional, default: `jira_issues`)

## Agent API

`/agent` runs a LangGraph flow that fetches a Jira issue and uses ChatGroq to answer your question from that issue context.

Example request:

```json
{
	"message": "What is the current status and summary?",
	"issue_id": "TEST-5"
}
```

## Jira batch ingestion

The ingestion pipeline reads Jira issues in batches and upserts these fields into Postgres:

- `id`
- `key`
- `summary`
- `description`

Run:

```bash
uv run python -m backlog_generation.data_ingestion_pipeline
```
