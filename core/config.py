"""
Global configuration for UE5 AI Assistant.
"""
import os
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Автоматически настраиваем Tesseract
_tess_cmd = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if Path(_tess_cmd).exists():
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _tess_cmd
    except ImportError:
        pass


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
WORKFLOWS_DIR = DATA_DIR / "workflows"
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"

# Ensure dirs exist
for d in [DATA_DIR, LOGS_DIR, WORKFLOWS_DIR, ASSETS_DIR, ICONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class LLMConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"           # Recommended: fast + smart
    fallback_model: str = "llama3:8b"
    temperature: float = 0.1            # Low = more deterministic
    max_tokens: int = 2048


class VisionConfig(BaseModel):
    capture_interval_ms: int = 500       # Screenshot every 500ms
    ocr_language: str = "eng"
    confidence_threshold: float = 0.75  # Min confidence for UI detection


class MemoryConfig(BaseModel):
    db_path: str = str(DATA_DIR / "assistant.db")
    chroma_path: str = str(DATA_DIR / "chroma")
    embedding_model: str = "all-MiniLM-L6-v2"
    max_workflow_history: int = 1000


class UIConfig(BaseModel):
    overlay_width: int = 420
    overlay_height: int = 600
    icon_size: int = 56
    always_on_top: bool = True
    opacity: float = 0.95
    theme: str = "dark"                  # dark | light
    position: str = "bottom_right"       # bottom_right | bottom_left | top_right


class SafetyConfig(BaseModel):
    confirm_destructive_actions: bool = True
    destructive_keywords: list[str] = [
        "delete", "remove", "destroy", "clear", "reset", "wipe"
    ]
    backup_before_risky_ops: bool = True
    max_retries: int = 3


class Config(BaseModel):
    app_name: str = "UE5 AI Assistant"
    version: str = "0.1.0"
    debug: bool = False
    offline_mode: bool = False           # True = never use internet

    llm: LLMConfig = LLMConfig()
    vision: VisionConfig = VisionConfig()
    memory: MemoryConfig = MemoryConfig()
    ui: UIConfig = UIConfig()
    safety: SafetyConfig = SafetyConfig()


# Global singleton
config = Config()
