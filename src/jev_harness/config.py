"""Explicit, lazy configuration. Importing this module never creates a client."""
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen3.8-27b-mlx"
    llm_api_key: str = field(default="lm-studio", repr=False)
    llm_timeout: float = 120
    max_tokens: int = 1536
    jev_token: str = field(default="", repr=False)
    jev_model: str = "jev-latest"
    jev_timeout: float = 30
    data_dir: Path = Path("artifacts")
    risk_threshold: float = 1.0

    @classmethod
    def from_env(cls):
        load_dotenv(override=False)
        return cls(
            base_url=os.getenv("LOCAL_LLM_BASE_URL", cls.base_url),
            model=os.getenv("LOCAL_LLM_MODEL", cls.model),
            llm_api_key=os.getenv("LOCAL_LLM_API_KEY", "lm-studio"),
            llm_timeout=float(os.getenv("LOCAL_LLM_TIMEOUT", "120")),
            max_tokens=int(os.getenv("LOCAL_LLM_MAX_TOKENS", "1536")),
            jev_token=os.getenv("JEV_TOKEN") or os.getenv("TYPESAFE_API_KEY", ""),
            jev_model=os.getenv("JEV_MODEL", "jev-latest"),
            jev_timeout=float(os.getenv("JEV_TIMEOUT", "30")),
            data_dir=Path(os.getenv("JEV_LAB_DATA_DIR", "artifacts")),
        )

    def safe_error(self, error: Exception) -> str:
        text = str(error)
        for secret in (self.jev_token, self.llm_api_key):
            if secret:
                text = text.replace(secret, "[redacted]")
        return f"{type(error).__name__}: {text[:700]}"

    def execution_identity(self) -> dict:
        """Non-secret settings that must remain fixed across approval resumes."""
        return {"base_url": self.base_url, "model": self.model, "max_tokens": self.max_tokens,
                "llm_timeout": self.llm_timeout, "temperature": 0,
                "jev_model": self.jev_model, "jev_timeout": self.jev_timeout,
                "risk_threshold": self.risk_threshold}
