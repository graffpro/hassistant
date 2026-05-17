"""
PerfMonitor — следит за RAM/CPU/GPU и предупреждает заранее.

UE5 печально известен потреблением ресурсов. Монитор:
  - RAM > 85% → предупреждение + предложение закрыть лишнее
  - RAM > 95% → критично, предлагает сохранить и закрыть
  - CPU > 95% надолго → предупреждение о перегреве
  - Диск C: < 5GB → предупреждение (UE5 пишет кэш на C:)
  - UE5 процесс > 80% RAM → конкретная информация

Проверка каждые 30 сек. Предупреждение не чаще раза в 10 мин.
"""
import time
import threading
from typing import Optional

from core.logger import logger
from core.event_bus import bus, Events


class PerfMonitor:
    """Мониторит системные ресурсы и предупреждает о проблемах."""

    CHECK_INTERVAL   = 30.0
    WARN_COOLDOWN    = 600.0    # предупреждение раз в 10 мин

    # Пороги
    RAM_WARN_PCT     = 85
    RAM_CRIT_PCT     = 95
    CPU_WARN_PCT     = 95
    DISK_WARN_GB     = 5.0
    UE5_RAM_WARN_GB  = 12.0    # если UE5 берёт больше 12GB

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_warn: dict[str, float] = {}
        self._psutil_ok = False
        self._check_psutil()

    def start(self):
        if not self._psutil_ok:
            logger.warning("psutil not available — perf monitor disabled")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Performance monitor started")

    def stop(self):
        self._running = False

    def get_stats(self) -> dict:
        """Возвращает текущие системные метрики."""
        if not self._psutil_ok:
            return {}
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            disk = psutil.disk_usage("C:\\")

            ue5_ram = self._get_ue5_ram_gb()

            return {
                "ram_pct":   mem.percent,
                "ram_used":  round(mem.used / 1e9, 1),
                "ram_total": round(mem.total / 1e9, 1),
                "cpu_pct":   cpu,
                "disk_free": round(disk.free / 1e9, 1),
                "ue5_ram":   ue5_ram,
            }
        except Exception:
            return {}

    def status_message(self) -> str:
        """Форматирует текущее состояние системы."""
        s = self.get_stats()
        if not s:
            return "⚙️ Статистика недоступна (psutil не установлен)"

        lines = [
            f"💻 Состояние системы:",
            f"  🧠 RAM: {s['ram_used']}GB / {s['ram_total']}GB ({s['ram_pct']:.0f}%)",
            f"  ⚡ CPU: {s['cpu_pct']:.0f}%",
            f"  💾 Диск C: {s['disk_free']:.1f}GB свободно",
        ]
        if s.get("ue5_ram"):
            lines.append(f"  🎮 UE5 RAM: {s['ue5_ram']:.1f}GB")

        # Предупреждения
        if s["ram_pct"] > self.RAM_CRIT_PCT:
            lines.append(f"  🔴 КРИТИЧНО: RAM почти полная!")
        elif s["ram_pct"] > self.RAM_WARN_PCT:
            lines.append(f"  🟡 RAM заканчивается")
        if s["disk_free"] < self.DISK_WARN_GB:
            lines.append(f"  🟡 Мало места на C:")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────

    def _check_psutil(self):
        try:
            import psutil
            self._psutil_ok = True
        except ImportError:
            self._psutil_ok = False
            # Пробуем установить тихо
            try:
                import subprocess, sys
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "psutil", "--quiet"],
                    check=False, timeout=30,
                )
                import psutil  # noqa
                self._psutil_ok = True
            except Exception:
                pass

    def _loop(self):
        while self._running:
            try:
                self._check()
            except Exception as e:
                logger.debug(f"Perf monitor error: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _check(self):
        import psutil
        now = time.time()
        mem  = psutil.virtual_memory()
        cpu  = psutil.cpu_percent(interval=1.0)
        disk = psutil.disk_usage("C:\\")

        def cooldown_ok(key: str) -> bool:
            return now - self._last_warn.get(key, 0) > self.WARN_COOLDOWN

        # ── RAM критическая ──────────────────────────────────
        if mem.percent >= self.RAM_CRIT_PCT and cooldown_ok("ram_crit"):
            self._last_warn["ram_crit"] = now
            free_gb = round((mem.total - mem.used) / 1e9, 1)
            bus.emit(Events.STATUS_UPDATE, {
                "status": "error",
                "message": (
                    f"🔴 Критически мало RAM: {mem.percent:.0f}% занято ({free_gb}GB свободно)!\n"
                    f"💡 Сохрани проект и закрой лишние программы.\n"
                    f"Скажи 'сохрани' — сохраню проект прямо сейчас."
                ),
            })

        # ── RAM предупреждение ────────────────────────────────
        elif mem.percent >= self.RAM_WARN_PCT and cooldown_ok("ram_warn"):
            self._last_warn["ram_warn"] = now
            ue5_ram = self._get_ue5_ram_gb()
            ue5_str = f" (UE5: {ue5_ram:.1f}GB)" if ue5_ram else ""
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (
                    f"🟡 RAM заканчивается: {mem.percent:.0f}%{ue5_str}\n"
                    f"Рекомендую сохранить проект."
                ),
            })

        # ── CPU перегрев ─────────────────────────────────────
        if cpu >= self.CPU_WARN_PCT and cooldown_ok("cpu"):
            self._last_warn["cpu"] = now
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": f"🟡 CPU загружен на {cpu:.0f}% — возможно тормоза.",
            })

        # ── Мало места на диске ───────────────────────────────
        free_gb = disk.free / 1e9
        if free_gb < self.DISK_WARN_GB and cooldown_ok("disk"):
            self._last_warn["disk"] = now
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (
                    f"🟡 Мало места на диске C: {free_gb:.1f}GB свободно.\n"
                    f"UE5 пишет кэш на C: — может тормозить или упасть."
                ),
            })

        # ── UE5 сам берёт много RAM ───────────────────────────
        ue5_ram = self._get_ue5_ram_gb()
        if ue5_ram and ue5_ram > self.UE5_RAM_WARN_GB and cooldown_ok("ue5_ram"):
            self._last_warn["ue5_ram"] = now
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (
                    f"🟡 UE5 использует {ue5_ram:.1f}GB RAM.\n"
                    f"Если тормозит — попробуй закрыть лишние панели."
                ),
            })

    def _get_ue5_ram_gb(self) -> Optional[float]:
        """Возвращает RAM используемую UE5 процессом в GB."""
        try:
            import psutil
            for proc in psutil.process_iter(["name", "memory_info"]):
                if "UnrealEditor" in proc.info["name"]:
                    return proc.info["memory_info"].rss / 1e9
        except Exception:
            pass
        return None
