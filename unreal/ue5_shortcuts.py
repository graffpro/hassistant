"""
Все горячие клавиши Unreal Engine 5.
"""
from dataclasses import dataclass


@dataclass
class Shortcut:
    keys: str           # "Ctrl+S"
    description: str
    context: str        # "global" | "blueprint" | "viewport" | "content_browser"


UE5_SHORTCUTS: dict[str, Shortcut] = {
    # === ГЛОБАЛЬНЫЕ ===
    "save":             Shortcut("Ctrl+S",       "Сохранить текущий ассет",           "global"),
    "save_all":         Shortcut("Ctrl+Shift+S", "Сохранить все ассеты",              "global"),
    "undo":             Shortcut("Ctrl+Z",        "Отменить",                          "global"),
    "redo":             Shortcut("Ctrl+Y",        "Повторить",                         "global"),
    "content_browser":  Shortcut("Ctrl+B",        "Открыть Content Browser",           "global"),
    "play":             Shortcut("F5",            "Запустить PIE (Play In Editor)",    "global"),
    "play_alt":         Shortcut("Alt+P",         "Запустить PIE (альтернатива)",      "global"),
    "stop":             Shortcut("Escape",        "Остановить PIE",                    "global"),
    "simulate":         Shortcut("Alt+S",         "Запустить Simulate",               "global"),
    "build_all":        Shortcut("Ctrl+Shift+,",  "Build All (освещение и т.д.)",     "global"),
    "open_project":     Shortcut("Ctrl+O",        "Открыть проект",                    "global"),
    "new_level":        Shortcut("Ctrl+N",        "Новый уровень",                     "global"),
    "open_level":       Shortcut("Ctrl+Shift+O",  "Открыть уровень",                  "global"),
    "find_in_blueprints": Shortcut("Ctrl+Shift+F", "Поиск по всем Blueprint",         "global"),
    "output_log":       Shortcut("Ctrl+Shift+L",  "Открыть Output Log",               "global"),

    # === VIEWPORT ===
    "focus_selection":  Shortcut("F",            "Сфокусироваться на выделении",      "viewport"),
    "translate":        Shortcut("W",            "Инструмент перемещения",            "viewport"),
    "rotate":           Shortcut("E",            "Инструмент вращения",               "viewport"),
    "scale":            Shortcut("R",            "Инструмент масштабирования",        "viewport"),
    "snap_to_grid":     Shortcut("End",          "Прикрепить к поверхности",         "viewport"),
    "duplicate":        Shortcut("Ctrl+W",       "Дублировать актор",                "viewport"),
    "delete_actor":     Shortcut("Delete",       "Удалить выделенный актор",         "viewport"),
    "group":            Shortcut("Ctrl+G",       "Сгруппировать",                    "viewport"),
    "hide_selected":    Shortcut("H",            "Скрыть выделенное",                "viewport"),
    "show_all":         Shortcut("Ctrl+H",       "Показать всё",                     "viewport"),
    "camera_speed":     Shortcut("Ctrl+Shift+K", "Настройки камеры",                 "viewport"),

    # === BLUEPRINT EDITOR ===
    "compile_bp":       Shortcut("F7",           "Скомпилировать Blueprint",          "blueprint"),
    "find_in_bp":       Shortcut("Ctrl+F",       "Поиск в Blueprint",                "blueprint"),
    "toggle_debug":     Shortcut("F9",           "Установить точку останова",        "blueprint"),
    "zoom_to_fit":      Shortcut("Home",         "Вписать граф в экран",             "blueprint"),
    "align_top":        Shortcut("Ctrl+Shift+T", "Выровнять узлы по верху",          "blueprint"),
    "create_comment":   Shortcut("C",            "Создать комментарий",              "blueprint"),
    "collapse_nodes":   Shortcut("Ctrl+Shift+C", "Свернуть узлы в функцию",          "blueprint"),

    # === CONTENT BROWSER ===
    "rename_asset":     Shortcut("F2",           "Переименовать ассет",              "content_browser"),
    "delete_asset":     Shortcut("Delete",       "Удалить ассет",                    "content_browser"),
    "duplicate_asset":  Shortcut("Ctrl+D",       "Дублировать ассет",               "content_browser"),
    "import_asset":     Shortcut("Ctrl+I",       "Импортировать ассет",             "content_browser"),
    "refresh_cb":       Shortcut("F5",           "Обновить Content Browser",         "content_browser"),

    # === MATERIAL EDITOR ===
    "compile_mat":      Shortcut("Ctrl+Shift+C", "Применить/скомпилировать материал", "material"),
    "find_in_mat":      Shortcut("Ctrl+F",       "Поиск в материале",               "material"),
}


def get_shortcut(action: str) -> str:
    """Возвращает клавиши для действия."""
    s = UE5_SHORTCUTS.get(action)
    return s.keys if s else ""


def find_shortcut_by_description(query: str) -> list[Shortcut]:
    """Поиск шортката по описанию."""
    q = query.lower()
    return [s for s in UE5_SHORTCUTS.values() if q in s.description.lower()]


def get_context_shortcuts(context: str) -> dict[str, Shortcut]:
    """Все шорткаты для контекста."""
    return {k: v for k, v in UE5_SHORTCUTS.items() if v.context in (context, "global")}
