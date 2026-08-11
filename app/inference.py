"""Client for DO Serverless Inference (OpenAI-compatible, https://inference.do-ai.run).

A client-level timeout is set here as defense in depth, but the mechanism the
worker actually relies on is its own wall-clock deadline (see
worker.run_with_deadline) — that catches a stuck call regardless of whether the
client library's own timeout implementation is trustworthy, which is the
posture you want for "sometimes it just hangs and we don't know why."
"""

import os

from openai import OpenAI

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("INFERENCE_BASE_URL", "https://inference.do-ai.run/v1"),
            api_key=os.environ["INFERENCE_API_KEY"],
            timeout=float(os.environ.get("INFERENCE_CLIENT_TIMEOUT_SECONDS", "60")),
        )
    return _client


def call_model(prompt: str) -> str:
    """The one real model call per job. Deliberately trivial — this is a
    stand-in workload, not a contract parser."""
    model = os.environ.get("INFERENCE_MODEL", "llama3.3-70b-instruct")
    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
    )
    return response.choices[0].message.content
