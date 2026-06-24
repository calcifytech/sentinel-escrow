import os
from dataclasses import dataclass
from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

# Make sure we override any existing env vars with .env settings (critical for GOOGLE_API_KEY override in testing)
load_dotenv(override=True)

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")

@dataclass
class AgentConfig:
    model_name: str = os.getenv("GEMINI_MODEL", "openrouter/google/gemini-2.5-flash")
    mcp_server_port: int = 8090
    max_iterations: int = 3
    pii_redaction_enabled: bool = True
    injection_detection_enabled: bool = True

    @property
    def model(self):
        key = os.getenv("GOOGLE_API_KEY")
        if key:
            key = key.strip("<>")
        return LiteLlm(
            model=self.model_name,
            api_key=key,
            api_base="https://openrouter.ai/api/v1",
            max_tokens=1000  # Set max_tokens to prevent 402 payment errors on OpenRouter free/low-tier accounts
        )

config = AgentConfig()
