"""
ErrorFixer — AI-powered система исправления ошибок установки.
Сначала rule-based (быстро), потом LLM (когда Ollama доступен).
"""
import re
import subprocess
import sys
from typing import Optional


# ─────────────────────────────────────────────────────────────
# БАЗА ЗНАНИЙ ОШИБОК И ИСПРАВЛЕНИЙ
# ─────────────────────────────────────────────────────────────
ERROR_RULES: list[dict] = [
    # pip / network
    {
        "patterns": ["connection error", "timeout", "network", "ssl", "certificate"],
        "description": "Проблема с сетью / SSL",
        "fixes": [
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--trusted-host", "pypi.org",
                         "--trusted-host", "files.pythonhosted.org", "-q"],
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--retries", "5", "-q"],
        ]
    },
    # версия пакета
    {
        "patterns": ["requires python", "python version", "not supported"],
        "description": "Несовместимая версия Python",
        "fixes": [
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--no-deps", "-q"],
        ]
    },
    # уже установлен
    {
        "patterns": ["already satisfied", "already installed"],
        "description": "Уже установлен",
        "fixes": []   # не ошибка
    },
    # нет прав
    {
        "patterns": ["permission denied", "access denied", "errno 13", "errno 5"],
        "description": "Нет прав доступа",
        "fixes": [
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--user", "-q"],
        ]
    },
    # нет диска
    {
        "patterns": ["no space left", "disk full", "errno 28"],
        "description": "Нет места на диске",
        "fixes": []  # пользователь должен освободить место
    },
    # нет подходящей версии
    {
        "patterns": ["no matching distribution", "could not find", "not find a version"],
        "description": "Пакет не найден — пробую старую версию",
        "fixes": [
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg.split("==")[0], "-q"],
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--pre", "-q"],
        ]
    },
    # wheels / build error
    {
        "patterns": ["error: legacy-install-failure", "building wheel", "failed to build", "error: command"],
        "description": "Ошибка компиляции — пробую pre-built wheel",
        "fixes": [
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--only-binary=:all:", "-q"],
            lambda pkg: [sys.executable, "-m", "pip", "install", pkg, "--prefer-binary", "-q"],
        ]
    },
    # winget недоступен
    {
        "patterns": ["winget", "not recognized", "'winget' is not"],
        "description": "winget недоступен — использую прямую загрузку",
        "fixes": []
    },
]

# Альтернативные имена пакетов
PACKAGE_ALTERNATIVES: dict[str, list[str]] = {
    "chromadb":             ["chromadb==0.4.24", "chromadb==0.4.18"],
    "sentence-transformers": ["sentence_transformers", "sentence-transformers==2.2.2"],
    "openai-whisper":       ["openai-whisper==20231117", "whisper"],
    "PyQt6":                ["PyQt6==6.6.1", "PyQt6==6.5.3"],
    "opencv-python":        ["opencv-python-headless", "opencv-python==4.8.1.78"],
    "pywin32":              ["pywin32==306", "pywin32==305"],
}


class ErrorFixer:
    def __init__(self, log_callback=None):
        self._log = log_callback or print
        self._ollama_available = False

    def set_ollama_available(self, available: bool):
        self._ollama_available = available

    def fix_pip_install(self, package: str, error_output: str) -> tuple[bool, str]:
        """
        Пытается исправить ошибку pip install.
        Возвращает (success, message).
        """
        error_lower = error_output.lower()

        # Проверяем "уже установлен" — не ошибка
        if any(p in error_lower for p in ["already satisfied", "already installed"]):
            return True, "Уже установлен"

        # Ищем подходящее правило
        matched_rule = None
        for rule in ERROR_RULES:
            if any(p in error_lower for p in rule["patterns"]):
                matched_rule = rule
                break

        if matched_rule:
            self._log(f"    ⚡ Обнаружена ошибка: {matched_rule['description']}")

            if not matched_rule["fixes"]:
                return False, matched_rule["description"]

            # Пробуем каждый fix
            for fix_fn in matched_rule["fixes"]:
                cmd = fix_fn(package)
                self._log(f"    🔧 Пробую: {' '.join(cmd[-3:])}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self._log(f"    ✓ Исправлено!")
                    return True, "Исправлено"

        # Пробуем альтернативные имена пакета
        base_pkg = package.split("==")[0].split(">=")[0].strip()
        if base_pkg in PACKAGE_ALTERNATIVES:
            for alt in PACKAGE_ALTERNATIVES[base_pkg]:
                self._log(f"    🔄 Пробую альтернативу: {alt}")
                cmd = [sys.executable, "-m", "pip", "install", alt, "-q"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self._log(f"    ✓ Установлено через альтернативу: {alt}")
                    return True, f"Установлено как {alt}"

        # LLM анализ (если Ollama доступен)
        if self._ollama_available:
            return self._llm_fix(package, error_output)

        return False, f"Не удалось установить {package}"

    def _llm_fix(self, package: str, error: str) -> tuple[bool, str]:
        """Просит LLM предложить решение ошибки установки."""
        try:
            import requests
            prompt = (f"Python pip install error for package '{package}':\n{error[:500]}\n\n"
                      f"Suggest ONE specific pip install command to fix this. "
                      f"Reply with ONLY the pip arguments, nothing else. "
                      f"Example: 'install chromadb==0.4.18 --no-deps -q'")

            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
                timeout=20,
            )
            if resp.ok:
                suggestion = resp.json().get("response", "").strip()
                if suggestion and "install" in suggestion.lower():
                    args = re.sub(r'^pip\s+', '', suggestion).strip()
                    cmd = [sys.executable, "-m", "pip"] + args.split()
                    self._log(f"    🤖 AI предлагает: pip {args}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        self._log("    ✓ AI исправление сработало!")
                        return True, "Исправлено AI"
        except Exception as e:
            pass
        return False, "AI не смог исправить"

    def diagnose_system(self) -> list[str]:
        """Диагностирует систему и возвращает список проблем."""
        issues = []

        # Python версия
        if sys.version_info < (3, 11):
            issues.append(f"Python {sys.version_info.major}.{sys.version_info.minor} — нужен 3.11+")

        # pip
        result = subprocess.run([sys.executable, "-m", "pip", "--version"],
                                 capture_output=True, text=True)
        if result.returncode != 0:
            issues.append("pip недоступен")

        # Место на диске C:
        try:
            import shutil
            free_gb = shutil.disk_usage("C:").free / (1024**3)
            if free_gb < 20:
                issues.append(f"Мало места на диске: {free_gb:.1f} GB (нужно 20+ GB для моделей)")
        except Exception:
            pass

        # Интернет
        try:
            import urllib.request
            urllib.request.urlopen("https://pypi.org", timeout=5)
        except Exception:
            issues.append("Нет доступа к интернету или PyPI заблокирован")

        return issues
