import streamlit as st
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

st.set_page_config(page_title="Catalyst UI", page_icon="⚡", layout="centered")

st.title("Catalyst")
st.caption("Simple Streamlit UI for the Catalyst agent")

API_URL = "http://localhost:8000/agent"

issue_id = st.text_input("Issue ID", placeholder="TEST-5")
message = st.text_area("Message", placeholder="What is the current status and summary?")

if st.button("Run Agent", type="primary"):
    if not issue_id.strip() or not message.strip():
        st.warning("Please enter both Issue ID and Message.")
    else:
        with st.spinner("Running agent..."):
            try:
                payload = json.dumps(
                    {"message": message.strip(), "issue_id": issue_id.strip()}
                ).encode("utf-8")
                request = Request(
                    API_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urlopen(request, timeout=60) as response:
                    response_data = json.loads(response.read().decode("utf-8"))

                st.subheader("Response")
                st.write(response_data.get("response", "No response field in API output."))
            except HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="ignore")
                st.error(f"FastAPI returned HTTP {exc.code}: {error_body}")
            except URLError as exc:
                st.error(f"Could not connect to FastAPI at {API_URL}. Details: {exc.reason}")
            except Exception as exc:
                st.error(f"Agent failed: {exc}")
