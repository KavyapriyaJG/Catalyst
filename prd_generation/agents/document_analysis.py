from config import get_settings
from prd_generation.state import AgentState
from utils.document_utils import build_documents, retrieve_context


def analyze_documents(s: AgentState):
    """Analyze uploaded documents using semantic search and context retrieval."""
    print("\n[Step 1/4] Analyzing uploaded documents...")
    documents = s.get("documents", [])

    if not documents:
        print("   No documents provided")
        return {"document_analysis": "No documents uploaded."}

    try:
        doc_objects = build_documents(documents)
        print(f"   Built {len(doc_objects)} document objects")
        queries = [
            "What are the main requirements and functional specifications?",
            "What are the key processes and workflows described?",
            "What data structures and entities are mentioned?",
            "What are the business rules and constraints?",
            "What are the technical specifications and dependencies?",
            "What are the integration points and external systems?",
        ]

        insights = []
        for q in queries:
            try:
                context = retrieve_context(q, doc_objects, top_k=get_settings().SEMANTIC_TOP_K)
                if context:
                    insights.append(f"**{q}**\n{context}")
            except Exception as e:
                print(f"   Query '{q}' failed: {e}")

        doc_analysis = (
            "\n\n---\n\n".join(insights)
            if insights
            else "Unable to extract meaningful insights from documents."
        )
        print(f"   Document analysis complete ({len(doc_analysis)} chars)")
        return {"document_analysis": doc_analysis}

    except Exception as e:
        print(f"   Error during document analysis: {e}")
        return {"document_analysis": f"Error analyzing documents: {e}"}
