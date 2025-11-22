# app/middleware/guardrails_middleware.py
"""
Guardrails Middleware for FastAPI
Integrates promptfoo-style safety checks and content moderation.

This middleware can:
1. Check inputs for malicious content, PII, prompt injection, etc.
2. Validate outputs for safety issues
3. Log violations for security monitoring
4. Block or moderate unsafe requests/responses
"""

import os
import re
import json
import yaml
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class GuardrailsConfig:
    """Configuration for guardrails from YAML file."""

    def __init__(self, config_path: str = "guardrails.yaml"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load guardrails configuration from YAML file."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Guardrails config not found: {self.config_path}")
            return self._get_default_config()

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded guardrails config from {self.config_path}")
                return config
        except Exception as e:
            logger.error(f"Error loading guardrails config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Get default guardrails configuration."""
        return {
            "enabled": True,
            "mode": "moderate",  # strict, moderate, permissive
            "input_checks": {
                "pii_detection": True,
                "prompt_injection": True,
                "harmful_content": True,
                "excessive_length": True,
                "max_length": 10000,
            },
            "output_checks": {
                "pii_leakage": True,
                "harmful_content": True,
                "hallucination_detection": False,  # Requires special models
            },
            "blocked_patterns": [],
            "allowed_endpoints": ["/health", "/docs", "/openapi.json"],
        }


class GuardrailsChecker:
    """Performs various safety checks on content."""

    # Common PII patterns
    PII_PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b(\+\d{1,2}\s?)?(\()?\d{3}(\))?[\s.-]?\d{3}[\s.-]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        "api_key": r'\b(sk-|pk-|api[_-]?key[_-]?)[a-zA-Z0-9]{20,}\b',
    }

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?previous\s+(instructions|commands|rules)',
        r'system\s*:\s*you\s+are',
        r'forget\s+(everything|all|previous)',
        r'new\s+instructions',
        r'disregard\s+(all\s+)?(previous|prior)',
        r'admin\s+mode',
        r'developer\s+mode',
        r'jailbreak',
        r'roleplay\s+as',
    ]

    # Harmful content keywords
    HARMFUL_KEYWORDS = [
        "exploit", "hack", "bypass", "vulnerability", "injection",
        "malware", "ransomware", "phishing", "credentials",
    ]

    @staticmethod
    def check_pii(text: str) -> Dict[str, Any]:
        """Check for Personal Identifiable Information."""
        violations = []
        for pii_type, pattern in GuardrailsChecker.PII_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                violations.append({
                    "type": "pii",
                    "subtype": pii_type,
                    "count": len(matches),
                    "severity": "high",
                })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
        }

    @staticmethod
    def check_prompt_injection(text: str) -> Dict[str, Any]:
        """Check for prompt injection attempts."""
        violations = []
        for pattern in GuardrailsChecker.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append({
                    "type": "prompt_injection",
                    "pattern": pattern,
                    "severity": "high",
                })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
        }

    @staticmethod
    def check_harmful_content(text: str) -> Dict[str, Any]:
        """Check for potentially harmful content."""
        violations = []
        text_lower = text.lower()

        for keyword in GuardrailsChecker.HARMFUL_KEYWORDS:
            if keyword in text_lower:
                violations.append({
                    "type": "harmful_content",
                    "keyword": keyword,
                    "severity": "medium",
                })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
        }

    @staticmethod
    def check_length(text: str, max_length: int = 10000) -> Dict[str, Any]:
        """Check if text exceeds maximum length."""
        violations = []
        if len(text) > max_length:
            violations.append({
                "type": "excessive_length",
                "length": len(text),
                "max_allowed": max_length,
                "severity": "low",
            })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
        }


class GuardrailsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that applies guardrails to requests and responses.

    This middleware can be configured to check:
    - Input: PII, prompt injection, harmful content, excessive length
    - Output: PII leakage, harmful content

    Configuration is loaded from guardrails.yaml
    """

    def __init__(self, app, config_path: str = "guardrails.yaml"):
        super().__init__(app)
        self.config = GuardrailsConfig(config_path)
        self.checker = GuardrailsChecker()
        self.enabled = self.config.config.get("enabled", True)

        if self.enabled:
            logger.info("Guardrails middleware enabled")
        else:
            logger.info("Guardrails middleware disabled")

    async def dispatch(self, request: Request, call_next):
        """Process request and response through guardrails."""
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip allowed endpoints
        if request.url.path in self.config.config.get("allowed_endpoints", []):
            return await call_next(request)

        # Check input
        input_result = await self._check_input(request)
        if not input_result["passed"]:
            return self._create_violation_response(input_result)

        # Process request
        response = await call_next(request)

        # Check output if needed
        if self.config.config.get("output_checks", {}).get("pii_leakage") or \
           self.config.config.get("output_checks", {}).get("harmful_content"):
            response = await self._check_output(response)

        return response

    async def _check_input(self, request: Request) -> Dict[str, Any]:
        """Check request input for violations."""
        violations = []

        # Get request body if it exists
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Try to parse as JSON
                    try:
                        data = json.loads(body)
                        # Extract text fields
                        text_content = self._extract_text_from_dict(data)
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text
                        text_content = body.decode("utf-8", errors="ignore")

                    # Re-populate request body for downstream handlers
                    async def receive():
                        return {"type": "http.request", "body": body}

                    request._receive = receive

                    # Perform checks
                    input_checks = self.config.config.get("input_checks", {})

                    if input_checks.get("pii_detection"):
                        result = self.checker.check_pii(text_content)
                        if not result["passed"]:
                            violations.extend(result["violations"])

                    if input_checks.get("prompt_injection"):
                        result = self.checker.check_prompt_injection(text_content)
                        if not result["passed"]:
                            violations.extend(result["violations"])

                    if input_checks.get("harmful_content"):
                        result = self.checker.check_harmful_content(text_content)
                        if not result["passed"]:
                            violations.extend(result["violations"])

                    if input_checks.get("excessive_length"):
                        max_len = input_checks.get("max_length", 10000)
                        result = self.checker.check_length(text_content, max_len)
                        if not result["passed"]:
                            violations.extend(result["violations"])

            except Exception as e:
                logger.error(f"Error checking input: {e}")

        # Determine if request should be blocked
        mode = self.config.config.get("mode", "moderate")
        should_block = False

        if mode == "strict":
            should_block = len(violations) > 0
        elif mode == "moderate":
            # Block only high severity violations
            should_block = any(v.get("severity") == "high" for v in violations)
        # permissive mode doesn't block

        if violations:
            logger.warning(f"Guardrails violations detected: {violations}")

        return {
            "passed": not should_block,
            "violations": violations,
            "mode": mode,
        }

    async def _check_output(self, response: Response) -> Response:
        """Check response output for violations (currently limited)."""
        # Output checking is more complex and may require buffering the response
        # For now, we'll skip it to avoid performance issues
        # In production, you might integrate with promptfoo's grading API
        return response

    def _extract_text_from_dict(self, data: Any, max_depth: int = 5) -> str:
        """Recursively extract text content from dictionary/list."""
        if max_depth <= 0:
            return ""

        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            texts = []
            for value in data.values():
                texts.append(self._extract_text_from_dict(value, max_depth - 1))
            return " ".join(texts)
        elif isinstance(data, list):
            texts = []
            for item in data:
                texts.append(self._extract_text_from_dict(item, max_depth - 1))
            return " ".join(texts)
        else:
            return str(data)

    def _create_violation_response(self, result: Dict[str, Any]) -> JSONResponse:
        """Create error response for violations."""
        return JSONResponse(
            status_code=400,
            content={
                "error": "Request blocked by guardrails",
                "mode": result.get("mode"),
                "violations": result.get("violations", []),
                "message": "Your request was blocked due to safety policy violations.",
            },
        )
