"""
Helper for summarizing git diffs using the OpenAI API.

Uses the OpenAI Python SDK with simple retry logic. Expects OPENAI_API_KEY
to be set in the environment. Only standard library plus `openai` are used.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from openai import OpenAI, OpenAIError


DEFAULT_MODEL = os.getenv("WATCHER_MODEL", "gpt-4o-mini")
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def summarize_diff(diff_text: str) -> str:
    """
    Summarize a unified diff using an OpenAI chat model.

    Returns a fallback message if summarization fails after retries.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "No OPENAI_API_KEY set; skipping summary."

    client = OpenAI(api_key=api_key)
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise changelog assistant. "
                            "Summarize code diffs into a short, clear note."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Summarize the following git diff. "
                            "Be brief and concrete. Mention key files or functions touched.\n\n"
                            f"{diff_text}"
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=200,
            )

            summary = response.choices[0].message.content or ""
            return summary.strip()
        except OpenAIError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            else:
                break
        except Exception as exc:  # Safety net for unexpected errors
            last_error = exc
            break

    return f"Summary unavailable (error: {last_error})" if last_error else "Summary unavailable."


__all__ = ["summarize_diff"]
