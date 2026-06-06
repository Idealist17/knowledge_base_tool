from __future__ import annotations
from dataclasses import dataclass, field
import os


@dataclass
class LLMConfig:
    # Read environment at instantiation time, after dotenv has been loaded by CLI.
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
    api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    request_timeout: float = field(default_factory=lambda: float(os.getenv("OPENAI_REQUEST_TIMEOUT", "120")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("OPENAI_MAX_RETRIES", "5")))
    input_token_budget: int = 24000
    merge_chunk_candidate_token_budget: int = 12000
    finding_token_budget: int = 16000
