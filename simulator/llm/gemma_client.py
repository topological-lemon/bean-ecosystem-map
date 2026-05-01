"""
gemma_client.py
===============
Minimal client for calling Gemma via Ollama's local API.

In dev, points at localhost:11434 (Ollama default).
In production (HF Space), the OLLAMA_HOST env var will redirect to
the hosted inference endpoint without code changes.

Note: Gemma 4 e2b/e4b handle the `system` parameter inconsistently in
Ollama's API. We merge the system instruction into the user prompt for
reliability, which works across all Gemma 4 variants.
"""

import os
import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("GEMMA_MODEL", "gemma4:e2b")


def generate(prompt, system=None, temperature=0.7, max_tokens=1024):
    """Send a prompt to Gemma and return the response text.

    If `system` is provided, it is prepended to the prompt with a clear
    role separator. This is more reliable across Gemma 4 variants than
    the dedicated `system` API parameter.
    """
    if system:
        full_prompt = f"{system}\n\nUser question: {prompt}"
    else:
        full_prompt = prompt

    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json=payload,
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


if __name__ == "__main__":
    system = (
        "You are an ecologist explaining peat-swamp forest dynamics to "
        "policy makers. Be specific about Sabangau-relevant species. Cite "
        "mechanisms, not generalities."
    )
    prompt = (
        "If Bornean orangutans (Pongo pygmaeus wurmbii) are extirpated from "
        "the Sabangau peat-swamp forest, what specific cascading effects "
        "occur in the seed dispersal network within the first 10 years? "
        "Name three concrete plant species likely to decline and explain why."
    )
    print("Sending prompt to Gemma...")
    print("---")
    response = generate(prompt, system=system, max_tokens=1024)
    print(response)
    print("---")
    print(f"Response length: {len(response)} chars")
