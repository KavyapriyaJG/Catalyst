# Catalyst

Catalyst is an **AI-Driven SDLC** platform.

## Current module

Currently, Catalyst includes the **Backlog Generation** module.

This module currently provides:

- Jira issue context retrieval
- AI-assisted responses from Jira issue data
- Jira-to-Postgres batch ingestion using SQLAlchemy ORM

## Environment variables

Set the following environment variables:

- `JIRA_BASE_URL` (example: `https://your-domain.atlassian.net`)
- `JIRA_USERNAME` (your Jira/Atlassian email)
- `JIRA_AUTH_TOKEN` (Atlassian API token)
- `GROQ_API_KEY`
- `GROQ_MODEL` (optional, default: `llama-3.1-8b-instant`)
- `JIRA_FETCH_ISSUES_JQL` (optional, default: `project=TEST AND created>=-365d ORDER BY created DESC`)
- `JIRA_BATCH_SIZE` (optional, default: `50`, max: `100`)
- `JIRA_BATCHES_TO_BE_PROCESSED_COUNT` (optional, default: `10`)
- `POSTGRES_DSN` (example: `postgresql://user:password@localhost:5432/dbname`)
- `ORM_ECHO_SQL` (optional: `false`, `true`, or `debug`)

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

The ingestion pipeline reads Jira issues in batches and upserts data into PostgreSQL tables:

- `issues` (`id`, `issue_key`)
- `issue_hierarchy` (`parent_id`, `child_id`)
- `issue_links` (`source_id`, `target_id`, `link_type`)

Notes:

- Tables are created automatically via SQLAlchemy metadata.
- Issue rows are upserted with `ON CONFLICT (id) DO UPDATE`.
- Hierarchy and link rows are inserted with conflict-ignore semantics.

Run:

```bash
uv run python -m backlog_generation.data_ingestion_pipeline
```
