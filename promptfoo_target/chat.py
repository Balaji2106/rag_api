import os
import json
import requests

def call_api(prompt, options=None, context=None):
    """
    This is the function Promptfoo redteam expects.
    It receives the attack prompt and must return a JSON object with an 'output' key.

    This wrapper calls the /chat endpoint which:
    1. Retrieves relevant documents from vector store
    2. Generates an answer using LLM with RAG context
    3. Returns the generated answer
    """

    # Use /chat endpoint for LLM-generated responses
    rag_url = os.getenv("RAG_API_URL", "http://localhost:8000/chat")
    file_id = os.getenv("RAG_FILE_ID", "alice_in_wonderland.txt")

    payload = {
        "query": prompt,
        "file_id": file_id,
        "k": 4,
        "entity_id": None,
        "temperature": 0.7,
        "max_tokens": 1500
    }

    try:
        resp = requests.post(rag_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Extract answer from ChatResponse
        if isinstance(data, dict) and "answer" in data:
            answer = data["answer"]
        else:
            # Fallback to stringified response
            answer = json.dumps(data)

        # Wrap output in JSON the way Promptfoo expects
        return {"output": answer}

    except requests.exceptions.Timeout:
        return {"output": "Error: Request timed out"}
    except requests.exceptions.HTTPError as e:
        return {"output": f"Error: HTTP {e.response.status_code} - {e.response.text}"}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
