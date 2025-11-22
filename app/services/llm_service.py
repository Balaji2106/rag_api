# app/services/llm_service.py
"""
LLM Service for generating answers from RAG context.
Supports multiple LLM providers: Azure OpenAI, OpenAI, Google, Ollama, etc.
"""

import os
import logging
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    AZURE_OPENAI = "azure"
    OPENAI = "openai"
    GOOGLE_GENAI = "google_genai"
    GOOGLE_VERTEXAI = "vertexai"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"


class LLMService:
    """
    Flexible LLM service that generates answers from RAG context.
    Can be configured to use different LLM providers.
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.AZURE_OPENAI,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ):
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model or self._get_default_model()
        self.client = self._initialize_client()

    def _get_default_model(self) -> str:
        """Get default model based on provider."""
        defaults = {
            LLMProvider.AZURE_OPENAI: os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            LLMProvider.OPENAI: os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            LLMProvider.GOOGLE_GENAI: os.getenv("GOOGLE_MODEL", "gemini-pro"),
            LLMProvider.GOOGLE_VERTEXAI: os.getenv("VERTEXAI_MODEL", "gemini-pro"),
            LLMProvider.OLLAMA: os.getenv("OLLAMA_MODEL", "llama2"),
            LLMProvider.BEDROCK: os.getenv("BEDROCK_MODEL", "anthropic.claude-v2"),
        }
        return defaults.get(self.provider, "gpt-4o-mini")

    def _initialize_client(self):
        """Initialize the appropriate LLM client based on provider."""
        try:
            if self.provider == LLMProvider.AZURE_OPENAI:
                from langchain_openai import AzureChatOpenAI

                return AzureChatOpenAI(
                    deployment_name=self.model,
                    api_key=os.getenv("RAG_AZURE_OPENAI_API_KEY"),
                    azure_endpoint=os.getenv("RAG_AZURE_OPENAI_ENDPOINT"),
                    api_version=os.getenv("RAG_AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

            elif self.provider == LLMProvider.OPENAI:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=self.model,
                    api_key=os.getenv("RAG_OPENAI_API_KEY"),
                    base_url=os.getenv("RAG_OPENAI_BASEURL"),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

            elif self.provider == LLMProvider.GOOGLE_GENAI:
                from langchain_google_genai import ChatGoogleGenerativeAI

                return ChatGoogleGenerativeAI(
                    model=self.model,
                    google_api_key=os.getenv("RAG_GOOGLE_API_KEY"),
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                )

            elif self.provider == LLMProvider.GOOGLE_VERTEXAI:
                from langchain_google_vertexai import ChatVertexAI

                return ChatVertexAI(
                    model=self.model,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                )

            elif self.provider == LLMProvider.OLLAMA:
                from langchain_ollama import ChatOllama

                return ChatOllama(
                    model=self.model,
                    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
                    temperature=self.temperature,
                )

            elif self.provider == LLMProvider.BEDROCK:
                from langchain_aws import ChatBedrock
                import boto3

                session = boto3.Session(
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
                )

                return ChatBedrock(
                    model_id=self.model,
                    client=session.client("bedrock-runtime"),
                    model_kwargs={
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                    },
                )

            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")

        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            raise

    def generate_answer(
        self,
        query: str,
        context_documents: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate an answer using RAG context.

        Args:
            query: User's question
            context_documents: List of relevant document chunks from vector search
            system_prompt: Optional custom system prompt

        Returns:
            Generated answer as string
        """
        try:
            # Build context from documents
            context = self._build_context(context_documents)

            # Use default system prompt if none provided
            if not system_prompt:
                system_prompt = self._get_default_system_prompt()

            # Build user message
            user_message = f"""Context from documents:
{context}

Question: {query}

Please provide a precise, accurate answer based solely on the context above. If the context doesn't contain enough information to answer the question, say so."""

            # Generate response
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            response = self.client.invoke(messages)

            # Extract content from response
            if hasattr(response, "content"):
                return response.content
            else:
                return str(response)

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise

    def _build_context(self, documents: List[Dict]) -> str:
        """Build context string from document chunks."""
        if not documents:
            return "No relevant context found."

        context_parts = []
        for i, doc_data in enumerate(documents[:5], 1):  # Limit to top 5 chunks
            # Handle both tuple (doc, score) and dict formats
            if isinstance(doc_data, (list, tuple)) and len(doc_data) >= 1:
                doc = doc_data[0]
                score = doc_data[1] if len(doc_data) > 1 else None
            else:
                doc = doc_data
                score = None

            # Extract content
            if isinstance(doc, dict):
                content = doc.get("page_content", "")
                metadata = doc.get("metadata", {})
            elif hasattr(doc, "page_content"):
                content = doc.page_content
                metadata = getattr(doc, "metadata", {})
            else:
                content = str(doc)
                metadata = {}

            # Add to context
            source_info = f"[Source {i}"
            if metadata.get("file_id"):
                source_info += f" - {metadata['file_id']}"
            if score is not None:
                source_info += f" - Relevance: {score:.3f}"
            source_info += "]"

            context_parts.append(f"{source_info}\n{content}")

        return "\n\n".join(context_parts)

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for RAG."""
        return """You are a helpful AI assistant that answers questions based on provided context.

Your role:
1. Provide accurate, precise answers based ONLY on the given context
2. If the context doesn't contain sufficient information, clearly state that
3. Do not make up information or use knowledge outside the provided context
4. Keep answers concise and relevant to the question
5. Cite sources when possible using the [Source N] references

Remember: Be truthful, accurate, and helpful."""


# Singleton instance (can be configured via environment variables)
def get_llm_service() -> LLMService:
    """
    Get configured LLM service instance.
    Configuration via environment variables:
    - LLM_PROVIDER: azure, openai, google_genai, vertexai, ollama, bedrock
    - LLM_MODEL: Model name/deployment
    - LLM_TEMPERATURE: Temperature (0.0-1.0)
    - LLM_MAX_TOKENS: Maximum response tokens
    """
    provider_str = os.getenv("LLM_PROVIDER", "azure").lower()
    provider = LLMProvider(provider_str)

    return LLMService(
        provider=provider,
        model=os.getenv("LLM_MODEL"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1500")),
    )
