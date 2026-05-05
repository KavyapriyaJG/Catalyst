import base64
import json
import urllib.parse
import urllib.request
from dotenv import load_dotenv

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict
from config import get_settings

load_dotenv()

class IssueState(TypedDict):
    title: str
    summary: str
    assignee: str
    status: str
    creator: str
    reporter: str


class GraphState(TypedDict):
    message: str
    response: str
    issue_id: str
    issue: IssueState


def _empty_issue_state() -> IssueState:
    return IssueState(
        title="",
        summary="",
        assignee="",
        status="",
        creator="",
        reporter="",
    )


def _get_jira_config() -> tuple[str, str, str]:
    s = get_settings()
    if not s.JIRA_BASE_URL or not s.JIRA_USERNAME or not s.JIRA_AUTH_TOKEN:
        raise ValueError(
            "Missing Jira credentials. Set JIRA_BASE_URL, JIRA_USERNAME, JIRA_AUTH_TOKEN."
        )
    return s.JIRA_BASE_URL, s.JIRA_USERNAME, s.JIRA_AUTH_TOKEN


def _basic_auth_value(username: str, token: str) -> str:
    return base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("utf-8")


def _fetch_jira_issue(issue_id: str) -> dict:
    jira_base_url, jira_username, jira_auth_token = _get_jira_config()
    issue_key = urllib.parse.quote(issue_id, safe="")
    fields = urllib.parse.quote("summary,assignee,status,creator,reporter", safe=",")
    endpoint = f"{jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}?fields={fields}"
    auth_value = _basic_auth_value(jira_username, jira_auth_token)
    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": f"Basic {auth_value}",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=get_settings().JIRA_ISSUE_FETCH_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_issue_state(issue_payload: dict) -> IssueState:
    fields = issue_payload.get("fields", {})
    summary = fields.get("summary") or ""

    assignee_data = fields.get("assignee") or {}
    creator_data = fields.get("creator") or {}
    reporter_data = fields.get("reporter") or {}
    status_data = fields.get("status") or {}

    return {
        "title": summary,
        "summary": summary,
        "assignee": assignee_data.get("displayName", ""),
        "status": status_data.get("name", ""),
        "creator": creator_data.get("displayName", ""),
        "reporter": reporter_data.get("displayName", ""),
    }


def _answer_with_chatgroq(question: str, issue_context: IssueState) -> str:
    s = get_settings()
    if not s.GROQ_API_KEY:
        raise ValueError("Missing GROQ_API_KEY environment variable.")

    from langchain_groq import ChatGroq

    llm = ChatGroq(model=s.GROQ_MODEL, api_key=s.GROQ_API_KEY, temperature=0)

    context_json = json.dumps(issue_context)
    prompt = (
        "You are a Jira assistant. Answer the user's question using only the Jira issue context. "
        "If the answer is not present in the context, say so clearly.\n\n"
        f"Jira issue context:\n{context_json}\n\n"
        f"User question: {question}"
    )
    return llm.invoke(prompt).content


def build_simple_graph():
    def process_message(state: GraphState) -> GraphState:
        return {
            "message": state["message"],
            "response": f"LangGraph received: {state['message']}",
            "issue_id": state["issue_id"],
            "issue": _empty_issue_state(),
        }

    def get_jira_issue(state: GraphState) -> GraphState:
        try:
            issue_payload = _fetch_jira_issue(state["issue_id"])
            issue_values: IssueState = _extract_issue_state(issue_payload)
            issue_response = "Jira issue fetched successfully."
        except Exception as error:
            issue_values = _empty_issue_state()
            issue_response = f"Issue fetch failed: {error}"

        return {
            "message": state["message"],
            "response": f"{state['response']} {issue_response}",
            "issue_id": state["issue_id"],
            "issue": issue_values,
        }

    def answer_question_from_issue(state: GraphState) -> GraphState:
        issue_context = state["issue"]

        if not any(issue_context.values()):
            answer = "Cannot answer because Jira issue context is unavailable."
        else:
            try:
                answer = _answer_with_chatgroq(state["message"], issue_context)
            except Exception as error:
                answer = f"LLM answer failed: {error}"

        return {
            "message": state["message"],
            "response": f"{state['response']} Answer: {answer}",
            "issue_id": state["issue_id"],
            "issue": state["issue"],
        }

    graph_builder = StateGraph(GraphState)
    graph_builder.add_node("process_message", process_message)
    graph_builder.add_node("get_jira_issue", get_jira_issue)
    graph_builder.add_node("answer_question_from_issue", answer_question_from_issue)
    graph_builder.add_edge(START, "process_message")
    graph_builder.add_edge("process_message", "get_jira_issue")
    graph_builder.add_edge("get_jira_issue", "answer_question_from_issue")
    graph_builder.add_edge("answer_question_from_issue", END)

    return graph_builder.compile()

def generate_graph_diagram(graph):
    from IPython.display import Image, display
    # Generate the image
    image_data = graph.get_graph().draw_mermaid_png()

    # Save to file
    with open("graph.png", "wb") as f:
        f.write(image_data)


def run_jira_qa_workflow(message: str, issue_id: str) -> str:
    graph = build_simple_graph()
    result = graph.invoke(
        {
            "message": message,
            "issue_id": issue_id,
            "response": "",
            "issue": _empty_issue_state(),
        }
    )
    generate_graph_diagram(graph)
    
    return result["response"]
