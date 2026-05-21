import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_core.prompts import ChatPromptTemplate

from api.models import DesignArtifactDetail, DesignArtifactListItem
from api.services.prd_service import extract_and_validate_documents, get_prd
from config import get_settings
from prd_generation.llm import get_llm_codex

SUPPORTED_DIAGRAM_TYPES = ("database", "api", "architecture")

_FILE_NAME_BY_TYPE = {
    "database": "database.dbml",
    "api": "api.yaml",
    "architecture": "architecture.mmd",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_llm_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()

    return str(content)


def _strip_markdown_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _prd_to_text(prd_content: dict) -> str:
    lines: list[str] = []
    for key, value in prd_content.items():
        lines.append(f"## {key}")
        if isinstance(value, str):
            lines.append(value)
        else:
            lines.append(json.dumps(value, indent=2))
        lines.append("")
    return "\n".join(lines).strip()


def _modernization_docs_to_text(modernization_documents: list[dict[str, str]]) -> str:
    sections: list[str] = []
    for doc in modernization_documents:
        name = doc.get("filename", "document")
        content = doc.get("content", "")
        sections.append(f"# Document: {name}\n{content}")
    return "\n\n".join(sections).strip()


def _truncate_for_prompt(value: str, max_chars: int = 12000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n... [truncated]"


def _load_context_artifacts(context_artifact_ids: list[str] | None) -> list[dict[str, str]]:
    if not context_artifact_ids:
        return []

    loaded: list[dict[str, str]] = []
    seen: set[str] = set()
    for artifact_id in context_artifact_ids:
        if artifact_id in seen:
            continue
        seen.add(artifact_id)

        try:
            artifact = get_design_artifact(artifact_id)
        except FileNotFoundError as error:
            raise ValueError(f"Context artifact not found: {artifact_id}") from error

        loaded.append(
            {
                "id": artifact.id,
                "diagram_type": artifact.diagram_type,
                "content": artifact.content,
                "explanation": artifact.explanation,
                "source": "provided",
            }
        )

    return loaded


def _build_cross_artifact_context(target_diagram_type: str, context_entries: list[dict[str, str]]) -> str:
    if not context_entries:
        return ""

    databases = [entry for entry in context_entries if entry.get("diagram_type") == "database"]
    apis = [entry for entry in context_entries if entry.get("diagram_type") == "api"]
    architectures = [entry for entry in context_entries if entry.get("diagram_type") == "architecture"]

    sections: list[str] = []

    if target_diagram_type == "api":
        if databases:
            lines = ["### Database Design Context (DBML + Explanation)"]
            for db in databases:
                lines.append(f"- Source: {db.get('source', 'unknown')} ({db['id']})")
                lines.append("DBML:")
                lines.append(_truncate_for_prompt(db.get("content", "")))
                lines.append("Explanation:")
                lines.append(_truncate_for_prompt(db.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

        if architectures:
            lines = ["### Architecture Context (Explanation)"]
            for arch in architectures:
                lines.append(f"- Source: {arch.get('source', 'unknown')} ({arch['id']})")
                lines.append(_truncate_for_prompt(arch.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

    elif target_diagram_type == "database":
        if architectures:
            lines = ["### Architecture Context (Explanation)"]
            for arch in architectures:
                lines.append(f"- Source: {arch.get('source', 'unknown')} ({arch['id']})")
                lines.append(_truncate_for_prompt(arch.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

        if apis:
            lines = ["### API Design Context"]
            for api in apis:
                lines.append(f"- Source: {api.get('source', 'unknown')} ({api['id']})")
                lines.append("OpenAPI:")
                lines.append(_truncate_for_prompt(api.get("content", "")))
                lines.append("Explanation:")
                lines.append(_truncate_for_prompt(api.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

    elif target_diagram_type == "architecture":
        if databases:
            lines = ["### Database Design Context"]
            for db in databases:
                lines.append(f"- Source: {db.get('source', 'unknown')} ({db['id']})")
                lines.append("DBML:")
                lines.append(_truncate_for_prompt(db.get("content", "")))
                lines.append("Explanation:")
                lines.append(_truncate_for_prompt(db.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

        if apis:
            lines = ["### API Design Context (Explanation)"]
            for api in apis:
                lines.append(f"- Source: {api.get('source', 'unknown')} ({api['id']})")
                lines.append(_truncate_for_prompt(api.get("explanation", ""), max_chars=6000))
            sections.append("\n".join(lines))

    return "\n\n".join(section for section in sections if section).strip()


def _fallback_api_yaml(artifact_name: str) -> str:
    return f'''openapi: "3.0.3"
info:
  title: "{artifact_name} API"
  version: "1.0.0"
paths:
  /health:
    get:
      summary: Health endpoint
      responses:
        "200":
          description: OK
components:
  schemas: {{}}
'''.strip()


def _fallback_dbml() -> str:
    return '''Table entities {
  id uuid [pk, not null]
  name varchar(120) [not null]
  created_at timestamp [not null]
}

Table events {
  id uuid [pk, not null]
  entity_id uuid [not null, ref: > entities.id]
  event_type varchar(80) [not null]
  event_time timestamp [not null]
}
'''.strip()


def _fallback_mermaid() -> str:
    return '''flowchart TD
  user[User]
  api[API Layer]
  service[Domain Service]
  db[(Database)]
  user --> api
  api --> service
  service --> db
'''.strip()


def _count_dbml_tables(content: str) -> int:
    return len(re.findall(r"\bTable\s+[A-Za-z_][\w]*\s*\{", content))


def _count_dbml_relationships(content: str) -> int:
    inline_refs = len(re.findall(r"\bref\s*:\s*>\s*[A-Za-z_][\w]*\.[A-Za-z_][\w]*", content, flags=re.IGNORECASE))
    explicit_refs = len(re.findall(r"\bRef\s*:", content))
    return inline_refs + explicit_refs


def _count_openapi_paths(content: str) -> int:
    try:
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            return 0
        paths = parsed.get("paths")
        if not isinstance(paths, dict):
            return 0
        return len(paths)
    except Exception:
        return 0


def _count_mermaid_nodes(content: str) -> int:
    # Approximate node count for flowchart-style mermaid declarations.
    return len(re.findall(r"\b[A-Za-z_][\w]*\[[^\]]+\]", content))


def _fallback_deep_explanation(
    diagram_type: str,
    prd_id: str,
    artifact_name: str,
    document_names: list[str],
    content: str,
) -> str:
    docs = ", ".join(document_names) if document_names else "none"
    if diagram_type == "database":
        table_count = _count_dbml_tables(content)
        rel_count = _count_dbml_relationships(content)
        return (
            f"# Database Design Explanation\n\n"
            f"## Context\n"
            f"This DBML was generated for **{artifact_name}** using PRD **{prd_id}** and modernization inputs: {docs}.\n\n"
            f"## Schema Summary\n"
            f"- Estimated tables: {table_count}\n"
            f"- Estimated relationships: {rel_count}\n"
            f"- Model style: normalized transactional core with explicit references\n\n"
            f"## Data Modeling Rationale\n"
            f"- Entities are separated to preserve domain boundaries and avoid duplicated state.\n"
            f"- Foreign-key style references are used to maintain referential integrity between aggregates.\n"
            f"- Primary keys are designed for stable identity and lifecycle-safe updates.\n\n"
            f"## Integrity, Performance, and Operations\n"
            f"- Add uniqueness constraints for external business identifiers where duplicate ingestion is possible.\n"
            f"- Add composite indexes for high-frequency filter+sort query paths.\n"
            f"- Plan growth strategy for event-like tables using partitioning when write volume scales.\n"
            f"- Keep audit metadata columns consistent across mutable entities for traceability.\n\n"
            f"## Suggested Review Checklist\n"
            f"1. Confirm cardinality for each relationship against business flows.\n"
            f"2. Validate nullable vs required attributes with downstream API contracts.\n"
            f"3. Verify index coverage for dashboard and reporting queries.\n"
            f"4. Confirm retention and archival strategy for high-volume entities."
        )

    if diagram_type == "api":
        endpoint_count = _count_openapi_paths(content)
        return (
            f"# API Design Explanation\n\n"
            f"## Context\n"
            f"This OpenAPI specification was generated for **{artifact_name}** using PRD **{prd_id}** and modernization inputs: {docs}.\n\n"
            f"## Contract Summary\n"
            f"- Estimated endpoint paths: {endpoint_count}\n"
            f"- Contract style: OpenAPI 3.0 YAML\n"
            f"- Focus: explicit request/response schemas and reusable components\n\n"
            f"## API Design Rationale\n"
            f"- Resource-oriented endpoints keep behavior predictable for clients.\n"
            f"- Schema-first definitions reduce ambiguity across frontend, backend, and QA teams.\n"
            f"- Reusable component schemas improve consistency and simplify version evolution.\n\n"
            f"## Security and Reliability Considerations\n"
            f"- Ensure auth requirements are explicit per operation, including public exceptions.\n"
            f"- Standardize error responses and validation payloads for debuggability.\n"
            f"- Apply pagination and filtering standards on list/history endpoints to protect latency.\n"
            f"- Add idempotency semantics for mutation endpoints where retries are expected.\n\n"
            f"## Suggested Review Checklist\n"
            f"1. Validate endpoint naming and resource boundaries against business capabilities.\n"
            f"2. Confirm request/response schemas match domain and persistence model.\n"
            f"3. Verify error model completeness (400/401/403/404/409/422/429).\n"
            f"4. Confirm backward-compatibility strategy for future versioning."
        )

    node_count = _count_mermaid_nodes(content)
    return (
        f"# Architecture Design Explanation\n\n"
        f"## Context\n"
        f"This Mermaid architecture diagram was generated for **{artifact_name}** using PRD **{prd_id}** and modernization inputs: {docs}.\n\n"
        f"## Topology Summary\n"
        f"- Estimated diagram nodes: {node_count}\n"
        f"- Representation: Mermaid graph/flowchart\n"
        f"- Focus: service boundaries, interaction paths, and data/system dependencies\n\n"
        f"## Architectural Rationale\n"
        f"- Component separation supports independent change and operational isolation.\n"
        f"- Directed edges express runtime dependencies and integration flow.\n"
        f"- The structure emphasizes clear boundary lines between interface, domain, and data concerns.\n\n"
        f"## Reliability and Operability Considerations\n"
        f"- Evaluate single points of failure and add redundancy for critical ingress paths.\n"
        f"- Define asynchronous boundaries where resilience and throughput are required.\n"
        f"- Add tracing and observability hooks along cross-service paths.\n"
        f"- Confirm security controls at trust boundaries and external integrations.\n\n"
        f"## Suggested Review Checklist\n"
        f"1. Validate each component responsibility against PRD scope.\n"
        f"2. Confirm dependency direction and data-flow correctness.\n"
        f"3. Review scaling assumptions for hot paths and high-volume interactions.\n"
        f"4. Validate failure handling and fallback paths for external dependencies."
    )


def _build_explanation(diagram_type: str, prd_id: str, artifact_name: str, document_names: list[str], content: str) -> str:
    docs = ", ".join(document_names) if document_names else "none"
    prompt_text = (
        "Write a deep, implementation-focused technical explanation in markdown for the generated artifact. "
        "Do not repeat the artifact verbatim. Explain rationale, structure, trade-offs, and review checklist.\n\n"
        f"Diagram type: {diagram_type}\n"
        f"Artifact name: {artifact_name}\n"
        f"PRD id: {prd_id}\n"
        f"Modernization docs: {docs}\n\n"
        "Generated artifact content:\n"
        f"{content}\n"
    )
    fallback = _fallback_deep_explanation(diagram_type, prd_id, artifact_name, document_names, content)
    return _generate_with_llm(prompt_text, fallback)


def _generate_with_llm(
    prompt_text: str,
    fallback: str,
    system_prompt: str = "You are an expert software architect. Return only the requested output format.",
) -> str:
    settings = get_settings()
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        return fallback

    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        chain = prompt | get_llm_codex()
        response = chain.invoke({"input": prompt_text})
        response_text = getattr(response, "text", None)
        if isinstance(response_text, str) and response_text.strip():
            content = response_text.strip()
        else:
            content = _coerce_llm_content_to_text(response.content).strip()
        content = _strip_markdown_fence(content)
        return content if content else fallback
    except Exception:
        return fallback


def _validate_api_yaml(content: str) -> str:
    parsed = yaml.safe_load(content)
    if not isinstance(parsed, dict):
        raise ValueError("Generated API spec did not parse to an object.")
    required = ("openapi", "info", "paths")
    missing = [key for key in required if key not in parsed]
    if missing:
        raise ValueError(f"Generated API spec missing keys: {', '.join(missing)}")
    return content


def _validate_dbml(content: str) -> str:
    if "Table " not in content:
        raise ValueError("Generated DBML did not include any Table declarations.")
    return content


def _validate_mermaid(content: str) -> str:
    first_non_empty = ""
    for line in content.splitlines():
        if line.strip():
            first_non_empty = line.strip()
            break
    if not re.match(r"^(graph|flowchart|sequenceDiagram|classDiagram|erDiagram|stateDiagram|journey|gantt|mindmap|timeline)\b", first_non_empty):
        raise ValueError("Generated Mermaid diagram did not start with a valid diagram declaration.")
    return content


def _sanitize_mermaid(content: str) -> str:
    normalized = content

    # Normalize escaped line breaks in labels.
    normalized = normalized.replace("\\n", "<br/>")

    # Mermaid 10.9.x parser is sensitive to parenthesized segments right after a break.
    normalized = re.sub(r"<br/>\(([^)]+)\)", r"<br/>\1", normalized)

    # Normalize unicode arrows often produced by LLMs.
    normalized = normalized.replace("→", "->").replace("↔", "<->")

    # Normalize classDef dasharray formatting.
    normalized = re.sub(r"stroke-dasharray:\s*(\d+)\s+(\d+)", r"stroke-dasharray: \1,\2", normalized)

    # Normalize dotted edge labels to quoted form.
    dotted_pattern = re.compile(r"^(\s*\w+)\s+-\.\s*([^\"].*?)\s*\.-(>?\s*\w+\s*)$", flags=re.MULTILINE)
    normalized = dotted_pattern.sub(lambda m: f'{m.group(1)} -. "{m.group(2).strip()}" .-{m.group(3)}', normalized)

    return normalized


def _artifact_dir(artifact_id: str) -> Path:
    root = get_settings().GENERATED_DESIGNS_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / artifact_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_artifact(
    *,
    group_id: str | None,
    prd_id: str,
    artifact_name: str,
    diagram_type: str,
    content: str,
    explanation: str,
    document_names: list[str],
) -> DesignArtifactListItem:
    artifact_id = str(uuid.uuid4())
    created_at = _utc_now_iso()
    updated_at = created_at

    directory = _artifact_dir(artifact_id)
    content_file_name = _FILE_NAME_BY_TYPE[diagram_type]
    explanation_file_name = "explanation.md"

    (directory / content_file_name).write_text(content, encoding="utf-8")
    (directory / explanation_file_name).write_text(explanation, encoding="utf-8")

    manifest = {
        "id": artifact_id,
        "group_id": group_id,
        "prd_id": prd_id,
        "artifact_name": artifact_name,
        "diagram_type": diagram_type,
        "status": "draft",
        "created_at": created_at,
        "updated_at": updated_at,
        "content_file": content_file_name,
        "explanation_file": explanation_file_name,
        "document_names": document_names,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return DesignArtifactListItem(
        id=artifact_id,
        group_id=group_id,
        prd_id=prd_id,
        artifact_name=artifact_name,
        diagram_type=diagram_type,
        status="draft",
        created_at=created_at,
        updated_at=updated_at,
    )


def _generate_api(prd_text: str, modernization_text: str, artifact_name: str, context_text: str) -> str:
    prompt_text = (
        "Generate OpenAPI 3.0 YAML from the following PRD and modernization document. "
        "Return only valid YAML with openapi, info, paths, requestBody and responses where needed, plus schemas.\n\n"
        f"PRD:\n{prd_text}\n\nModernization:\n{modernization_text}"
    )
    if context_text:
        prompt_text += (
            "\n\nCross-artifact context:\n"
            f"{context_text}\n\n"
            "Use this context to align API resources, payloads, and contracts."
        )
    generated = _generate_with_llm(prompt_text, _fallback_api_yaml(artifact_name))
    return _validate_api_yaml(generated)


def _generate_database(prd_text: str, modernization_text: str, context_text: str) -> str:
    prompt_text = (
        "Generate DBML for a production-grade relational schema from the following PRD and modernization document. "
        "Return only DBML with tables, keys, and references.\n\n"
        f"PRD:\n{prd_text}\n\nModernization:\n{modernization_text}"
    )
    if context_text:
        prompt_text += (
            "\n\nCross-artifact context:\n"
            f"{context_text}\n\n"
            "Use this context to align schema entities and relationships with system boundaries and API contracts."
        )
    generated = _generate_with_llm(prompt_text, _fallback_dbml())
    return _validate_dbml(generated)


def _generate_architecture(prd_text: str, modernization_text: str, context_text: str) -> str:
    mermaid_system_prompt = (
        "You are an expert software architect generating Mermaid diagrams that MUST parse reliably in Mermaid 10.9.6. "
        "Output only raw Mermaid code. Never output Markdown fences or prose."
    )

    prompt_text = (
        "Generate a stable Mermaid architecture diagram from the following PRD and modernization document.\n"
        "STRICT OUTPUT RULES:\n"
        "1. Return only Mermaid code, no markdown and no explanations.\n"
        "2. First non-empty line must be exactly one valid Mermaid declaration, typically `flowchart TB` or `flowchart LR`.\n"
        "3. Use ASCII arrows/operators only (`-->`, `<-->`, `-.->`, etc.); do not use unicode arrows.\n"
        "4. For multiline labels use `<br/>` and do not wrap the next line in parentheses right after `<br/>`.\n"
        "5. For dotted links with labels use quoted syntax like: `A -. \"label\" .-> B`.\n"
        "6. For `classDef` dash arrays use comma-separated format: `stroke-dasharray: 5,5`.\n"
        "7. Keep node ids alphanumeric/underscore and avoid spaces in ids.\n"
        "8. Use syntax valid for Mermaid 10.9.6 only.\n\n"
        f"PRD:\n{prd_text}\n\nModernization:\n{modernization_text}"
    )
    if context_text:
        prompt_text += (
            "\n\nCross-artifact context:\n"
            f"{context_text}\n\n"
            "Use this context to align component/data-flow boundaries with DB and API design intent."
        )
    generated = _generate_with_llm(prompt_text, _fallback_mermaid(), mermaid_system_prompt)
    sanitized = _sanitize_mermaid(generated)
    return _validate_mermaid(sanitized)


def generate_design_artifacts(
    *,
    prd_id: str,
    artifact_name: str | None,
    modernization_documents: list[dict] | None,
    context_artifact_ids: list[str] | None,
    diagram_types: list[str],
) -> list[DesignArtifactListItem]:
    if not modernization_documents:
        raise ValueError("modernization_documents is required.")

    invalid = [diagram_type for diagram_type in diagram_types if diagram_type not in SUPPORTED_DIAGRAM_TYPES]
    if invalid:
        raise ValueError(f"Unsupported diagram types: {', '.join(invalid)}")

    prd_item = get_prd(prd_id)
    prd_text = _prd_to_text(prd_item.content)

    docs = extract_and_validate_documents(modernization_documents)
    modernization_text = _modernization_docs_to_text(docs)
    document_names = [doc.get("filename", "document") for doc in docs]
    context_entries = _load_context_artifacts(context_artifact_ids)

    group_id = str(uuid.uuid4()) if len(diagram_types) > 1 else None
    base_name = (artifact_name or "Generated Design").strip() or "Generated Design"

    generated_items: list[DesignArtifactListItem] = []
    for diagram_type in diagram_types:
        context_text = _build_cross_artifact_context(diagram_type, context_entries)

        if diagram_type == "api":
            content = _generate_api(prd_text, modernization_text, base_name, context_text)
        elif diagram_type == "database":
            content = _generate_database(prd_text, modernization_text, context_text)
        else:
            content = _generate_architecture(prd_text, modernization_text, context_text)

        explanation = _build_explanation(diagram_type, prd_id, base_name, document_names, content)
        item = _save_artifact(
            group_id=group_id,
            prd_id=prd_id,
            artifact_name=base_name,
            diagram_type=diagram_type,
            content=content,
            explanation=explanation,
            document_names=document_names,
        )
        generated_items.append(item)

        # Make generate-all runs context-aware across artifacts generated in the same request.
        context_entries.append(
            {
                "id": item.id,
                "diagram_type": diagram_type,
                "content": content,
                "explanation": explanation,
                "source": "generated-in-run",
            }
        )

    return generated_items


def _read_manifest(manifest_path: Path) -> dict | None:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def list_design_artifacts() -> list[DesignArtifactListItem]:
    root = get_settings().GENERATED_DESIGNS_DIR
    if not root.exists():
        return []

    items: list[DesignArtifactListItem] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue

        manifest = _read_manifest(manifest_path)
        if not manifest:
            continue

        try:
            items.append(
                DesignArtifactListItem(
                    id=manifest["id"],
                    group_id=manifest.get("group_id"),
                    prd_id=manifest["prd_id"],
                    artifact_name=manifest["artifact_name"],
                    diagram_type=manifest["diagram_type"],
                    status=manifest.get("status", "draft"),
                    created_at=manifest["created_at"],
                    updated_at=manifest["updated_at"],
                )
            )
        except KeyError:
            continue

    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def get_design_artifact(artifact_id: str) -> DesignArtifactDetail:
    directory = get_settings().GENERATED_DESIGNS_DIR / artifact_id
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(artifact_id)

    manifest = _read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(artifact_id)

    content_file = directory / manifest["content_file"]
    explanation_file = directory / manifest["explanation_file"]
    if not content_file.exists() or not explanation_file.exists():
        raise FileNotFoundError(artifact_id)

    return DesignArtifactDetail(
        id=manifest["id"],
        group_id=manifest.get("group_id"),
        prd_id=manifest["prd_id"],
        artifact_name=manifest["artifact_name"],
        diagram_type=manifest["diagram_type"],
        status=manifest.get("status", "draft"),
        created_at=manifest["created_at"],
        updated_at=manifest["updated_at"],
        content=content_file.read_text(encoding="utf-8"),
        explanation=explanation_file.read_text(encoding="utf-8"),
    )
