from __future__ import annotations

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None


def count_tokens(text: str, model: str = "gpt-5.4-mini") -> int:
    if not text:
        return 0
    if tiktoken is None:
        return max(1, len(text) // 4)
    try:
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        try:
            enc = tiktoken.get_encoding("o200k_base")
        except Exception:
            return max(1, len(text) // 4)
    return len(enc.encode(text))


def chunk_text(text: str, token_budget: int, model: str = "gpt-5.4-mini") -> list[str]:
    if count_tokens(text, model) <= token_budget:
        return [text] if text else []
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    for para in paragraphs:
        candidate = "\n\n".join(current + [para])
        if current and count_tokens(candidate, model) > token_budget:
            chunks.append("\n\n".join(current))
            current = [para]
        elif count_tokens(para, model) > token_budget:
            if current:
                chunks.append("\n\n".join(current)); current = []
            approx = max(1000, token_budget * 3)
            for i in range(0, len(para), approx):
                chunks.append(para[i:i+approx])
        else:
            current.append(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def make_context_budget(model_max_input: int, system_tokens: int = 0, suffix_tokens: int = 0) -> int:
    return max(1000, int(model_max_input * 0.8) - system_tokens - suffix_tokens)
