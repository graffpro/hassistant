"""
UE5 AI Assistant — Installer
Полностью автономный установщик с AI error-fixing.
Упакован в Install.exe через PyInstaller.
"""
import os
import sys
import subprocess
import threading
import urllib.request
import tempfile
import time
import ctypes
from pathlib import Path

# tkinter встроен в Python — работает без установки
import tkinter as tk
from tkinter import ttk, scrolledtext

# Добавляем папку installer в путь
INSTALLER_DIR = Path(__file__).parent
sys.path.insert(0, str(INSTALLER_DIR))
from error_fixer import ErrorFixer

# ─────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ УСТАНОВКИ
# ─────────────────────────────────────────────────────────────

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Public")) / "UE5_Assistant"

PYTHON_URL   = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
OLLAMA_URL   = "https://ollama.com/download/OllamaSetup.exe"
TESSERACT_URL= "https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
VC_REDIST_URL= "https://aka.ms/vs/17/release/vc_redist.x64.exe"

PYTHON_PACKAGES = [
    ("PyQt6",                "Интерфейс ассистента"),
    ("PyQt6-Qt6",            "Qt6 runtime"),
    ("ollama",               "Ollama Python клиент"),
    ("openai-whisper",       "Распознавание голоса (Whisper)"),
    ("opencv-python",        "Компьютерное зрение"),
    ("pytesseract",          "OCR — чтение текста на экране"),
    ("Pillow",               "Работа с изображениями"),
    ("mss",                  "Снимки экрана"),
    ("pyautogui",            "Управление мышью и клавиатурой"),
    ("pywin32",              "Windows API"),
    ("comtypes",             "UI Automation"),
    ("pynput",               "Наблюдение за вводом"),
    ("chromadb",             "Векторная база памяти"),
    ("sentence-transformers","Семантический поиск"),
    ("yt-dlp",               "Загрузка YouTube видео"),
    ("sounddevice",          "Запись микрофона"),
    ("soundfile",            "Аудио файлы"),
    ("requests",             "HTTP / веб-поиск"),
    ("numpy",                "Математика и массивы"),
    ("pydantic",             "Валидация данных"),
    ("pydantic-settings",    "Настройки"),
    ("loguru",               "Логирование"),
    ("python-dotenv",        "Конфигурация .env"),
]

OLLAMA_MODELS = [
    ("qwen2.5:7b", "Главная AI модель (~4.7 GB)"),
    ("llava:7b",   "Vision модель для анализа изображений (~4.5 GB)"),
]

# ─────────────────────────────────────────────────────────────
# GUI УСТАНОВЩИКА
# ─────────────────────────────────────────────────────────────

class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UE5 AI Assistant — Установка")
        self.geometry("680x520")
        self.resizable(False, False)
        self.configure(bg="#0F0C1E")
        self._center_window()
        self._build_ui()
        self.fixer = ErrorFixer(log_callback=self._log)
        self._step = 0
        self._total_steps = 7
        self._running = False

    def _center_window(self):
        self.update_idletasks()
        w, h = 680, 520
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # Заголовок
        hdr = tk.Frame(self, bg="#1A0F3E", height=80)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🤖  UE5 AI Assistant", font=("Segoe UI", 20, "bold"),
                 fg="#C4B5FD", bg="#1A0F3E").pack(pady=12)
        tk.Label(hdr, text="Автономный установщик с AI исправлением ошибок",
                 font=("Segoe UI", 10), fg="#6B7280", bg="#1A0F3E").pack()

        # Текущий шаг
        self.step_var = tk.StringVar(value="Готов к установке")
        tk.Label(self, textvariable=self.step_var, font=("Segoe UI", 11, "bold"),
                 fg="#A78BFA", bg="#0F0C1E").pack(pady=(16, 4))

        # Прогресс-бар общий
        self.progress = ttk.Progressbar(self, length=580, mode="determinate",
                                         maximum=100, value=0)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar", troughcolor="#1A0F3E",
                         background="#7C3AED", thickness=14)
        self.progress.pack(pady=4)

        # Процент
        self.pct_var = tk.StringVar(value="0%")
        tk.Label(self, textvariable=self.pct_var, font=("Segoe UI", 9),
                 fg="#6B7280", bg="#0F0C1E").pack()

        # Под-прогресс (пакеты)
        self.sub_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.sub_var, font=("Segoe UI", 9),
                 fg="#4B5563", bg="#0F0C1E").pack()
        self.sub_progress = ttk.Progressbar(self, length=580, mode="determinate",
                                             maximum=100, value=0)
        self.sub_progress.pack(pady=2)

        # Лог
        log_frame = tk.Frame(self, bg="#0F0C1E")
        log_frame.pack(fill="both", expand=True, padx=20, pady=8)

        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=12, bg="#0A0718", fg="#9CA3AF",
            font=("Consolas", 9), relief="flat", bd=0,
            insertbackground="#7C3AED", state="disabled"
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_configure("ok",    foreground="#6EE7B7")
        self.log_box.tag_configure("warn",  foreground="#FCD34D")
        self.log_box.tag_configure("err",   foreground="#FCA5A5")
        self.log_box.tag_configure("step",  foreground="#C4B5FD", font=("Consolas", 9, "bold"))
        self.log_box.tag_configure("ai",    foreground="#A78BFA")

        # Кнопка старт
        self.start_btn = tk.Button(
            self, text="▶  Начать установку", font=("Segoe UI", 12, "bold"),
            bg="#7C3AED", fg="white", activebackground="#9D5CF6",
            relief="flat", bd=0, padx=20, pady=8, cursor="hand2",
            command=self._start_install
        )
        self.start_btn.pack(pady=10)

    def _log(self, msg: str, tag: str = ""):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _set_step(self, text: str, step: int):
        def _do():
            self.step_var.set(text)
            pct = int((step / self._total_steps) * 100)
            self.progress["value"] = pct
            self.pct_var.set(f"{pct}%")
        self.after(0, _do)

    def _set_sub(self, text: str, pct: int):
        def _do():
            self.sub_var.set(text)
            self.sub_progress["value"] = pct
        self.after(0, _do)

    def _done(self, success: bool):
        def _do():
            if success:
                self.step_var.set("✅  Установка завершена!")
                self.progress["value"] = 100
                self.pct_var.set("100%")
                self.start_btn.config(
                    text="🚀  Запустить ассистента",
                    bg="#059669",
                    command=self._launch_app
                )
            else:
                self.step_var.set("⚠️  Установка завершена с ошибками")
                self.start_btn.config(
                    text="🚀  Всё равно запустить",
                    bg="#D97706",
                    command=self._launch_app
                )
        self.after(0, _do)

    def _start_install(self):
        self.start_btn.config(state="disabled", text="Устанавливаю...")
        self._running = True
        thread = threading.Thread(target=self._install_all, daemon=True)
        thread.start()

    def _launch_app(self):
        script = INSTALL_DIR / "main.py"
        if script.exists():
            subprocess.Popen([sys.executable, str(script)],
                             cwd=str(INSTALL_DIR))
        self.destroy()

    # ─────────────────────────────────────────────────────────
    # УСТАНОВКА — ОСНОВНОЙ ПОТОК
    # ─────────────────────────────────────────────────────────

    def _install_all(self):
        all_ok = True

        # Диагностика
        self._log("🔍 Диагностика системы...", "step")
        issues = self.fixer.diagnose_system()
        if issues:
            for iss in issues:
                self._log(f"  ⚠ {iss}", "warn")
        else:
            self._log("  Система готова к установке", "ok")

        # Шаг 1 — Visual C++
        self._set_step("Шаг 1/7 — Visual C++ Redistributable", 0)
        self._log("\n▶ Шаг 1: Visual C++ Redistributable", "step")
        ok = self._install_vcredist()
        if not ok: all_ok = False

        # Шаг 2 — Python
        self._set_step("Шаг 2/7 — Python 3.11", 1)
        self._log("\n▶ Шаг 2: Python 3.11", "step")
        ok = self._install_python()
        if not ok: all_ok = False

        # Шаг 3 — Tesseract
        self._set_step("Шаг 3/7 — Tesseract OCR", 2)
        self._log("\n▶ Шаг 3: Tesseract OCR", "step")
        ok = self._install_tesseract()
        if not ok:
            self._log("  OCR будет отключён, ассистент продолжит работу", "warn")

        # Шаг 4 — Python пакеты
        self._set_step("Шаг 4/7 — Python библиотеки", 3)
        self._log("\n▶ Шаг 4: Python библиотеки", "step")
        ok = self._install_packages()
        if not ok: all_ok = False

        # Шаг 5 — Ollama
        self._set_step("Шаг 5/7 — Ollama AI сервер", 4)
        self._log("\n▶ Шаг 5: Ollama", "step")
        ok = self._install_ollama()
        if ok:
            self.fixer.set_ollama_available(True)

        # Шаг 6 — AI модели
        self._set_step("Шаг 6/7 — AI модели (большие файлы)", 5)
        self._log("\n▶ Шаг 6: AI модели", "step")
        self._pull_models()

        # Шаг 7 — Копируем проект + ярлык
        self._set_step("Шаг 7/7 — Финальная настройка", 6)
        self._log("\n▶ Шаг 7: Финальная настройка", "step")
        self._finalize()

        self._set_step("Готово!", 7)
        self._log("\n" + "="*50, "ok")
        self._log("  Установка завершена!", "ok")
        self._log("="*50, "ok")
        self._done(all_ok)

    # ─────────────────────────────────────────────────────────
    # ОТДЕЛЬНЫЕ ШАГИ
    # ─────────────────────────────────────────────────────────

    def _install_vcredist(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")
            val, _ = winreg.QueryValueEx(key, "Installed")
            if val == 1:
                self._log("  ✓ Уже установлен", "ok")
                return True
        except Exception:
            pass

        tmp = self._download("Visual C++ Redistributable", VC_REDIST_URL)
        if not tmp:
            return False
        result = subprocess.run([tmp, "/install", "/quiet", "/norestart"],
                                 capture_output=True)
        ok = result.returncode in (0, 3010)
        self._log(f"  {'✓ Установлен' if ok else '✗ Ошибка'}", "ok" if ok else "err")
        return ok

    def _install_python(self) -> bool:
        # Проверяем
        for cmd in ["python", "python3", "py"]:
            try:
                r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
                import re; m = re.search(r"3\.(\d+)", r.stdout)
                if m and int(m.group(1)) >= 11:
                    self._log(f"  ✓ {r.stdout.strip()} уже установлен", "ok")
                    return True
            except Exception:
                pass

        self._log("  Скачиваю Python 3.11.9...", "")
        tmp = self._download("Python 3.11.9", PYTHON_URL)
        if not tmp:
            return False
        result = subprocess.run(
            [tmp, "/quiet", "InstallAllUsers=1",
             "PrependPath=1", "Include_test=0"],
            capture_output=True
        )
        ok = result.returncode == 0
        if ok:
            # Обновляем PATH
            os.environ["PATH"] = subprocess.run(
                ["cmd", "/c", "echo %PATH%"],
                capture_output=True, text=True
            ).stdout.strip()
        self._log(f"  {'✓ Python установлен' if ok else '✗ Ошибка Python'}", "ok" if ok else "err")
        return ok

    def _install_tesseract(self) -> bool:
        tess_path = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if tess_path.exists():
            self._log("  ✓ Уже установлен", "ok")
            return True
        tmp = self._download("Tesseract OCR", TESSERACT_URL)
        if not tmp:
            return False
        result = subprocess.run([tmp, "/S"], capture_output=True)
        ok = result.returncode == 0
        self._log(f"  {'✓ Tesseract установлен' if ok else '✗ Ошибка'}", "ok" if ok else "warn")
        return ok

    def _install_packages(self) -> bool:
        total = len(PYTHON_PACKAGES)
        failed = []
        for i, (pkg, desc) in enumerate(PYTHON_PACKAGES):
            pct = int((i / total) * 100)
            self._set_sub(f"{desc} ({pkg})", pct)
            self._log(f"  [{i+1}/{total}] {desc}...", "")

            cmd = [sys.executable, "-m", "pip", "install", pkg, "-q",
                   "--disable-pip-version-check"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self._log(f"    ✓ OK", "ok")
            else:
                # AI исправление
                self._log(f"    ⚡ Ошибка — пробую исправить...", "ai")
                ok, msg = self.fixer.fix_pip_install(pkg, result.stderr + result.stdout)
                if ok:
                    self._log(f"    ✓ {msg}", "ok")
                else:
                    self._log(f"    ✗ Не удалось: {pkg}", "err")
                    failed.append(pkg)

        self._set_sub("", 100)
        if failed:
            self._log(f"  ⚠ Не установлено ({len(failed)}): {', '.join(failed)}", "warn")
        return len(failed) == 0

    def _install_ollama(self) -> bool:
        # Проверяем
        try:
            r = subprocess.run(["ollama", "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                self._log("  ✓ Ollama уже установлен", "ok")
                self._start_ollama_server()
                return True
        except Exception:
            pass

        tmp = self._download("Ollama", OLLAMA_URL)
        if not tmp:
            return False
        result = subprocess.run([tmp, "/S"], capture_output=True)
        ok = result.returncode == 0
        if ok:
            self._log("  ✓ Ollama установлен", "ok")
            time.sleep(2)
            self._start_ollama_server()
        else:
            self._log("  ✗ Ошибка установки Ollama", "err")
        return ok

    def _start_ollama_server(self):
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434", timeout=3)
            self._log("  ✓ Ollama сервер уже запущен", "ok")
        except Exception:
            subprocess.Popen(["ollama", "serve"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self._log("  ✓ Ollama сервер запущен", "ok")
            time.sleep(3)

    def _pull_models(self):
        for model, desc in OLLAMA_MODELS:
            self._log(f"  Скачиваю {model} — {desc}", "")
            self._log(f"  (Это займёт время — размер модели указан выше)", "warn")
            try:
                result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True, text=True, timeout=3600
                )
                if result.returncode == 0:
                    self._log(f"  ✓ {model} готов", "ok")
                else:
                    self._log(f"  ⚠ {model} — проблема со скачиванием", "warn")
                    self._log(f"    Запусти вручную: ollama pull {model}", "warn")
            except Exception as e:
                self._log(f"  ⚠ {model}: {e}", "warn")

    def _finalize(self):
        # Создаём ярлык на рабочем столе
        try:
            desktop = Path.home() / "Desktop"
            shortcut_path = desktop / "UE5 AI Assistant.bat"
            main_script = INSTALL_DIR / "main.py"
            shortcut_path.write_text(
                f'@echo off\ncd /d "{INSTALL_DIR}"\npython main.py\n',
                encoding="utf-8"
            )
            self._log("  ✓ Ярлык создан на рабочем столе", "ok")
        except Exception as e:
            self._log(f"  ⚠ Ярлык: {e}", "warn")

        # Добавляем Tesseract в .env
        env_file = INSTALL_DIR / ".env"
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            if "TESSERACT_CMD" not in content:
                env_file.write_text(
                    content + "\nTESSERACT_CMD=C:\\\\Program Files\\\\Tesseract-OCR\\\\tesseract.exe\n",
                    encoding="utf-8"
                )
        self._log("  ✓ Конфигурация обновлена", "ok")

    def _download(self, name: str, url: str) -> Optional[str]:
        """Скачивает файл во временную папку. Показывает прогресс."""
        self._log(f"  Скачиваю {name}...", "")
        import os as _os
        fd, tmp = tempfile.mkstemp(suffix=".exe")
        _os.close(fd)
        try:
            def reporthook(count, block, total):
                if total > 0:
                    pct = min(100, int(count * block * 100 / total))
                    self._set_sub(f"Скачиваю {name}... {pct}%", pct)

            urllib.request.urlretrieve(url, tmp, reporthook)
            self._set_sub("", 0)
            self._log(f"  ✓ Скачано", "ok")
            return tmp
        except Exception as e:
            self._log(f"  ✗ Ошибка загрузки {name}: {e}", "err")
            # Пробуем альтернативный URL через requests
            try:
                import requests
                r = requests.get(url, stream=True, timeout=30)
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                self._log(f"  ✓ Скачано (резервный метод)", "ok")
                return tmp
            except Exception as e2:
                self._log(f"  ✗ Резервная загрузка тоже не удалась: {e2}", "err")
                return None


# Для аннотации типов
from typing import Optional


# ─────────────────────────────────────────────────────────────
# ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    # Запрашиваем права администратора если нет
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
