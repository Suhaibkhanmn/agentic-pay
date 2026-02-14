"""
Gemini LLM client — uses the google-genai SDK for payment risk analysis.

Uses Gemini 2.5 Flash (fast, low token usage).
Runs synchronously via asyncio.to_thread() to avoid blocking FastAPI.
"""

import asyncio
import json
import logging
from typing import Optional

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentAssessment(BaseModel):
    """Structured output expected from Gemini."""

    risk_score: int  # 0-100
    risk_explanation: str
    should_escalate: bool
    suspicious_patterns: list[str]
    confidence: float  # 0.0-1.0


# ── Default fallback when LLM is unavailable ──
_DEFAULT_ASSESSMENT = AgentAssessment(
    risk_score=0,
    risk_explanation="LLM unavailable — defaulting to policy engine decision.",
    should_escalate=False,
    suspicious_patterns=[],
    confidence=0.0,
)

# ── System prompt with structured analysis framework ──
SYSTEM_PROMPT = (
    "You are a payment risk analyst for an AI-powered payment orchestration system.\n"
    "\n"
    "You receive: payment details, a vendor profile with historical stats, "
    "recent payment history, the policy engine verdict, and deterministic risk signals.\n"
    "\n"
    "ANALYSIS FRAMEWORK — evaluate each dimension:\n"
    "1. PATTERN FIT: Does this payment fit the vendor's historical pattern "
    "(amount, category, frequency)?\n"
    "2. SIGNAL CORRELATION: Are multiple risk signals correlated (genuinely "
    "suspicious) or coincidental (normal variation)?\n"
    "3. DESCRIPTION PLAUSIBILITY: Does the description/category make sense "
    "for this vendor and amount?\n"
    "4. HUMAN REVIEW HEURISTIC: Would a reasonable human reviewer want to "
    "see this before it goes through?\n"
    "\n"
    "RULES:\n"
    "- You can ONLY escalate (should_escalate=true) to send for human review.\n"
    "- You CANNOT override BLOCK or downgrade REQUIRE_APPROVAL.\n"
    "- Be conservative: when uncertain, escalate.\n"
    "- An empty risk signal list with a normal-looking payment should NOT be escalated.\n"
    "\n"
    "Return ONLY valid JSON:\n"
    '{"risk_score":<0-100>,"risk_explanation":"<brief>","should_escalate":<bool>,'
    '"suspicious_patterns":["..."],"confidence":<0.0-1.0>}'
)


def _call_gemini_sync(prompt: str) -> AgentAssessment:
    """Synchronous Gemini call — run via asyncio.to_thread()."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_budget=256),
            ),
        )

        # Extract text — handle various response shapes
        text = ""
        if response.text:
            text = response.text.strip()
        elif response.candidates:
            parts = response.candidates[0].content.parts
            if parts:
                text = parts[0].text.strip()

        if not text:
            logger.warning("Gemini returned empty response")
            return _DEFAULT_ASSESSMENT

        logger.info("Gemini raw response (%d chars): %s", len(text), text[:800])

        # Extract JSON object — Gemini 2.5 may wrap it in text/markdown
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            # Attempt to salvage truncated JSON by appending missing braces
            if start != -1 and end == -1:
                logger.warning(
                    "Gemini response truncated (no closing }), attempting repair"
                )
                # Close any open strings and the object
                repaired = text[start:].rstrip()
                # If it ends mid-string, close the string
                if repaired.count('"') % 2 != 0:
                    repaired += '"'
                # Close any open arrays
                open_brackets = repaired.count("[") - repaired.count("]")
                repaired += "]" * max(0, open_brackets)
                repaired += "}"
                try:
                    data = json.loads(repaired)
                    logger.info("Repaired truncated JSON successfully")
                    return AgentAssessment(**data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error("JSON repair failed: %s", e)
            logger.error("No JSON object found in Gemini response")
            return _DEFAULT_ASSESSMENT

        json_str = text[start : end + 1]
        data = json.loads(json_str)
        return AgentAssessment(**data)

    except ImportError:
        logger.warning("google-genai not installed, using default assessment")
        return _DEFAULT_ASSESSMENT
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini JSON response: %s", e)
        return _DEFAULT_ASSESSMENT
    except Exception as e:
        logger.error("Gemini API error: %s", e)
        return _DEFAULT_ASSESSMENT


async def analyze(prompt: str) -> AgentAssessment:
    """
    Async wrapper — calls Gemini in a thread pool so FastAPI stays non-blocking.
    Returns a default assessment if the API key is not configured.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set — skipping LLM analysis")
        return _DEFAULT_ASSESSMENT

    return await asyncio.to_thread(_call_gemini_sync, prompt)
