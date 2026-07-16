"""Configuration management for Memfault Analyzer."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean flag from the environment."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Application configuration."""

    MEMFAULT_API_KEY = os.getenv("MEMFAULT_API_KEY")
    MEMFAULT_ORG_SLUG = os.getenv("MEMFAULT_ORG_SLUG")
    MEMFAULT_PROJECT_SLUG = os.getenv("MEMFAULT_PROJECT_SLUG")
    MEMFAULT_API_BASE_URL = "https://api.memfault.com"

    AI_CLIENT = os.getenv("AI_CLIENT", "anthropic").strip().lower()
    AI_MODEL = os.getenv("AI_MODEL", "claude-opus-4-6").strip()

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    # Optional: Path to source code for enhanced analysis
    SOURCE_CODE_PATH = os.getenv("SOURCE_CODE_PATH")
    if SOURCE_CODE_PATH:
        SOURCE_CODE_PATH = Path(SOURCE_CODE_PATH)

    OUTPUT_DIR = Path("analysis_results")
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Safety gates for autonomous fix mode. Defaults are intentionally
    # non-mutating for public/open-source use.
    AUTONOMOUS_RUN_GIT_COMMANDS = _env_flag("MEMFAULT_AI_RUN_GIT_COMMANDS")
    AUTONOMOUS_APPLY_FIXES = _env_flag("MEMFAULT_AI_APPLY_FIXES")
    AUTONOMOUS_BUILD_FIXES = _env_flag("MEMFAULT_AI_BUILD_FIXES", True)
    AUTONOMOUS_COMMIT_FIXES = _env_flag("MEMFAULT_AI_COMMIT_FIXES")

    @classmethod
    def validate(cls):
        """Validate that all required configuration is present."""
        errors = []

        if not cls.MEMFAULT_API_KEY:
            errors.append("MEMFAULT_API_KEY is not set")
        if not cls.MEMFAULT_ORG_SLUG:
            errors.append("MEMFAULT_ORG_SLUG is not set")
        if not cls.MEMFAULT_PROJECT_SLUG:
            errors.append("MEMFAULT_PROJECT_SLUG is not set")
        if cls.AI_CLIENT != "anthropic":
            errors.append("AI_CLIENT must be set to 'anthropic' (the only supported client)")
        if not cls.AI_MODEL:
            errors.append("AI_MODEL is not set")
        if cls.AI_CLIENT == "anthropic" and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not set")

        if errors:
            raise ValueError(
                f"Missing required configuration:\n" + "\n".join(f"  - {e}" for e in errors) +
                "\n\nPlease create a .env file with these values (see .env.example)"
            )

        return True
