# app/routes/chat_routes.py
"""
Chat routes for RAG with LLM answer generation.
Combines vector search with LLM response generation.
"""

import traceback
from fastapi import APIRouter, Request, HTTPException, status
from functools import lru_cache

from app.config import logger, vector_store
from app.models import ChatRequestBody, ChatResponse
from app.services.vector_store.async_pg_vector import AsyncPgVector
from app.services.llm_service import get_llm_service, LLMService

router = APIRouter()


# Cache the embedding function
@lru_cache(maxsize=128)
def get_cached_query_embedding(query: str):
    return vector_store.embedding_function.embed_query(query)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_rag(
    body: ChatRequestBody,
    request: Request,
):
    """
    RAG endpoint with LLM answer generation.

    This endpoint:
    1. Performs vector similarity search to find relevant documents
    2. Passes the context to an LLM to generate a precise answer
    3. Returns the generated answer with source information

    The LLM provider can be configured via environment variables.
    """
    # Determine user authorization
    if not hasattr(request.state, "user"):
        user_authorized = body.entity_id if body.entity_id else "public"
    else:
        user_authorized = (
            body.entity_id if body.entity_id else request.state.user.get("id")
        )

    try:
        # Step 1: Get query embedding
        embedding = get_cached_query_embedding(body.query)

        # Step 2: Perform vector similarity search
        if isinstance(vector_store, AsyncPgVector):
            documents = await vector_store.asimilarity_search_with_score_by_vector(
                embedding,
                k=body.k,
                filter={"file_id": body.file_id},
                executor=request.app.state.thread_pool,
            )
        else:
            documents = vector_store.similarity_search_with_score_by_vector(
                embedding, k=body.k, filter={"file_id": body.file_id}
            )

        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No relevant documents found for the query",
            )

        # Step 3: Check authorization
        document, score = documents[0]
        doc_metadata = document.metadata
        doc_user_id = doc_metadata.get("user_id")

        authorized_documents = []
        if doc_user_id is None or doc_user_id == user_authorized:
            authorized_documents = documents
        else:
            # If using entity_id and access denied, try again with user's actual ID
            if body.entity_id and hasattr(request.state, "user"):
                user_authorized = request.state.user.get("id")
                if doc_user_id == user_authorized:
                    authorized_documents = documents
                else:
                    logger.warning(
                        f"Access denied for user {user_authorized} to document with user_id {doc_user_id}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have access to this document",
                    )
            else:
                logger.warning(
                    f"Unauthorized access attempt by user {user_authorized} to document with user_id {doc_user_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this document",
                )

        if not authorized_documents:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this document",
            )

        # Step 4: Initialize LLM service with custom parameters if provided
        llm_service = get_llm_service()

        # Override defaults if provided in request
        if body.temperature is not None:
            llm_service.temperature = body.temperature
            llm_service.client.temperature = body.temperature
        if body.max_tokens is not None:
            llm_service.max_tokens = body.max_tokens
            if hasattr(llm_service.client, 'max_tokens'):
                llm_service.client.max_tokens = body.max_tokens

        # Step 5: Generate answer using LLM
        answer = llm_service.generate_answer(
            query=body.query,
            context_documents=authorized_documents,
            system_prompt=body.system_prompt,
        )

        # Step 6: Return response
        return ChatResponse(
            answer=answer,
            query=body.query,
            file_id=body.file_id,
            sources_used=len(authorized_documents),
            model=llm_service.model,
        )

    except HTTPException as http_exc:
        logger.error(
            "HTTP Exception in chat_with_rag | Status: %d | Detail: %s",
            http_exc.status_code,
            http_exc.detail,
        )
        raise http_exc
    except Exception as e:
        logger.error(
            "Error in chat endpoint | File ID: %s | Query: %s | Error: %s | Traceback: %s",
            body.file_id,
            body.query,
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating answer: {str(e)}",
        )
