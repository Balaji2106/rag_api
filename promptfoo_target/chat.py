import os
import json
import requests

def call_api(prompt, options=None, context=None):
    """
    This is the function Promptfoo redteam expects.
    It receives the attack prompt and must return a JSON object with an 'output' key.
    """

    rag_url = os.getenv("RAG_API_URL", "http://localhost:8000/query")
    file_id = os.getenv("RAG_FILE_ID", "sample.txt")

    payload = {
        "query": prompt,
        "file_id": file_id,
        "k": 4,
        "entity_id": None
    }

    try:
        resp = requests.post(rag_url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Extract page_content from nested structure
        text = ""
        if isinstance(data, list) and len(data) > 0:
            first = data[0]  # [document, score]
            if isinstance(first, list) and len(first) > 0:
                doc = first[0]
                if isinstance(doc, dict) and "page_content" in doc:
                    text = doc["page_content"]

        if not text.strip():
            text = json.dumps(data)

        # Wrap output in JSON the way Promptfoo expects
        return {"output": text}

    except Exception as e:
        return {"output": f"Error: {str(e)}"}
