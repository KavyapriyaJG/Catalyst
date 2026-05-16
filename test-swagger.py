import streamlit as st
import yaml
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import streamlit.components.v1 as components

# -----------------------------
# LLM
# -----------------------------
llm = ChatOpenAI(
    model="gpt-5.3-codex",
    base_url="",
    api_key="",
    timeout=60,
    max_retries=2,
    temperature=0,
)

# -----------------------------
# Prompt
# -----------------------------
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are an expert OpenAPI generator.

Convert user requirements into valid OpenAPI 3.0 YAML.

Rules:
- Return ONLY YAML
- Include:
  - openapi
  - info
  - paths
  - requestBody
  - responses
- Add schemas where needed
- Make the YAML Swagger UI compatible
"""
    ),
    ("human", "{input}")
])

chain = prompt | llm


def _coerce_llm_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()

    return str(content)


def _extract_swagger_yaml(response) -> str:
    response_text = getattr(response, "text", None)
    if isinstance(response_text, str) and response_text.strip():
        content = response_text.strip()
    else:
        content = _coerce_llm_content_to_text(response.content).strip()

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return content

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("Text to Swagger Generator")

user_input = st.text_area(
    "Describe your API",
    height=250,
    placeholder="""
Example:
Create a user management API with:
- POST /users
- GET /users/{id}
- DELETE /users/{id}
User has:
- id
- name
- email
"""
)

if st.button("Generate Swagger"):
    with st.spinner("Generating OpenAPI spec..."):
        if not user_input.strip():
            st.warning("Enter an API description before generating Swagger.")
            st.stop()

        try:
            response = chain.invoke({
                "input": user_input
            })
            swagger_yaml = _extract_swagger_yaml(response)
            swagger_spec = yaml.safe_load(swagger_yaml)
        except yaml.YAMLError as exc:
            st.error("The generated response was not valid YAML.")
            st.exception(exc)
            st.stop()
        except Exception as exc:
            st.error("Failed to generate the OpenAPI spec.")
            st.exception(exc)
            st.stop()

        if not isinstance(swagger_spec, dict):
            st.error("The generated YAML did not parse into an OpenAPI object.")
            st.stop()

        # Swagger UI HTML
        swagger_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Swagger UI</title>

          <link rel="stylesheet"
            href="https://unpkg.com/swagger-ui-dist/swagger-ui.css" />

        </head>

        <body>

        <div id="swagger-ui"></div>

        <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
                <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-standalone-preset.js"></script>

        <script>
        window.onload = function() {{

                    const spec = {json.dumps(swagger_spec)};

          SwaggerUIBundle({{
            spec: spec,
            dom_id: '#swagger-ui',
                        presets: [
                            SwaggerUIBundle.presets.apis,
                            SwaggerUIStandalonePreset
                        ],
                        layout: 'BaseLayout',
          }});

        }};
        </script>

        </body>
        </html>
        """

        st.subheader("Swagger UI")

        components.html(
            swagger_html,
            height=800,
            scrolling=True
        )

        st.subheader("Generated Swagger YAML")

        st.code(swagger_yaml, language="yaml")