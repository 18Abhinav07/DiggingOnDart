"""Prompts of an exact token length, built with the server's own tokenizer and cached on disk.

All Qwen 2.5 sizes share one tokenizer, so a prompt built once is valid for every model in the matrix.
"""
from __future__ import annotations

import json

from . import config

SYSTEM = "You are a helpful assistant built into a web browser. Answer from the page the user is reading."
TASKS = {
    "summarise": "Summarise the page above in about 200 words, covering its main sections in order.",
    "extract": ("Extract every product, organisation and person named on the page above as JSON: "
                '{"products": [...], "organisations": [...], "people": [...]}. Output only the JSON.'),
}
E1B_QUESTIONS = [
    "What is the first topic the page covers?", "Name two organisations the page mentions.",
    "Which year is mentioned earliest?", "What does the page say about security?",
    "List three technical terms from the page.", "What is the page's last section about?",
    "Who are the people named on the page?", "What problem does the page describe?",
    "Give one number the page reports.", "What is the main claim of the second section?",
    "Which products does the page compare?", "What does the page say about memory?",
]


def chat(document: str, instruction: str) -> str:
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
            f"<|im_start|>user\n<page>\n{document}\n</page>\n\n{instruction}<|im_end|>\n"
            f"<|im_start|>assistant\n")


def _corpus() -> str:
    return (config.DATA_DIR / "context.txt").read_text()


def _cache_path(name: str):
    d = config.DATA_DIR / "prompts" / ("fake" if config.FAKE else "qwen2.5")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.json"


def _fit_document(server, target_tokens: int, instruction: str) -> tuple[str, int]:
    """Largest corpus prefix such that chat(doc, instruction) is exactly target_tokens long (or 1-2 under,
    where a token boundary does not split cleanly)."""
    overhead = len(server.tokenize(chat("", instruction)))
    corpus_tokens = server.tokenize(_corpus())
    n = target_tokens - overhead
    if n > len(corpus_tokens):
        raise ValueError(f"corpus too short for {target_tokens} tokens")
    for _ in range(8):
        doc = server.detokenize(corpus_tokens[:n])
        total = len(server.tokenize(chat(doc, instruction)))
        if total == target_tokens or (total < target_tokens and total >= target_tokens - 2):
            return doc, total
        n += target_tokens - total
    return doc, total


def build(server, ctx_tokens: int, task: str = "summarise") -> tuple[str, int]:
    """Return (prompt, n_tokens) for a context length and task."""
    path = _cache_path(f"{task}-{ctx_tokens}")
    if path.exists():
        d = json.loads(path.read_text())
        return d["prompt"], d["n_tokens"]
    doc, n = _fit_document(server, ctx_tokens, TASKS[task])
    prompt = chat(doc, TASKS[task])
    path.write_text(json.dumps({"prompt": prompt, "n_tokens": n}))
    return prompt, n


def build_warm(server, ctx_tokens: int) -> tuple[str, list[str], int]:
    """E1b: one shared page prefix plus short, distinct questions. Returns (prime_prompt, prompts, n_tokens)."""
    path = _cache_path(f"warm-{ctx_tokens}")
    if path.exists():
        d = json.loads(path.read_text())
        return d["prime"], d["prompts"], d["n_tokens"]
    longest = max(E1B_QUESTIONS, key=len)
    doc, n = _fit_document(server, ctx_tokens, longest)
    prime = chat(doc, "Read the page.")
    prompts = [chat(doc, q) for q in E1B_QUESTIONS]
    path.write_text(json.dumps({"prime": prime, "prompts": prompts, "n_tokens": n}))
    return prime, prompts, n
