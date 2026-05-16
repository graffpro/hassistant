"""
Встроенные шаблоны сложных UE5 workflows.
Готовые цепочки шагов для частых операций.
"""
from dataclasses import dataclass, field


@dataclass
class WorkflowTemplate:
    name: str
    description: str
    tags: list[str]
    steps: list[dict]               # Шаги как словари (сериализуемы)
    estimated_duration_sec: int = 10
    requires_ue5_version: str = "5.0"


# =====================================================
# ВСТРОЕННЫЕ WORKFLOW ШАБЛОНЫ
# =====================================================

BUILTIN_WORKFLOWS: dict[str, WorkflowTemplate] = {

    "create_blueprint_actor": WorkflowTemplate(
        name="create_blueprint_actor",
        description="Создать новый Blueprint Actor",
        tags=["create", "blueprint", "actor"],
        estimated_duration_sec=8,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                         "value": "Ctrl+B",     "description": "Открыть Content Browser",     "timeout_ms": 2000},
            {"step_id": 2, "action_type": "right_click", "target": "Content Browser Empty Area",      "value": None,         "description": "Контекстное меню",            "timeout_ms": 3000},
            {"step_id": 3, "action_type": "click",       "target": "Context Menu > New Blueprint Class", "value": None,    "description": "Создать Blueprint",           "timeout_ms": 4000},
            {"step_id": 4, "action_type": "click",       "target": "Blueprint Parent Class > Actor",  "value": None,         "description": "Родитель: Actor",             "timeout_ms": 5000},
            {"step_id": 5, "action_type": "type",        "target": "Blueprint Name Input",            "value": "{name}",     "description": "Ввести имя",                 "timeout_ms": 3000},
            {"step_id": 6, "action_type": "shortcut",    "target": "Global",                          "value": "Return",     "description": "Подтвердить",                "timeout_ms": 2000},
            {"step_id": 7, "action_type": "shortcut",    "target": "Global",                          "value": "Ctrl+S",     "description": "Сохранить",                  "timeout_ms": 3000},
        ]
    ),

    "create_blueprint_character": WorkflowTemplate(
        name="create_blueprint_character",
        description="Создать Blueprint Character (игровой персонаж)",
        tags=["create", "blueprint", "character", "player"],
        estimated_duration_sec=10,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                              "value": "Ctrl+B",  "description": "Открыть Content Browser",   "timeout_ms": 2000},
            {"step_id": 2, "action_type": "right_click", "target": "Content Browser Empty Area",           "value": None,      "description": "Контекстное меню",          "timeout_ms": 3000},
            {"step_id": 3, "action_type": "click",       "target": "Context Menu > New Blueprint Class",   "value": None,      "description": "Создать Blueprint",         "timeout_ms": 4000},
            {"step_id": 4, "action_type": "click",       "target": "Blueprint Parent Class > Character",   "value": None,      "description": "Родитель: Character",       "timeout_ms": 5000},
            {"step_id": 5, "action_type": "type",        "target": "Blueprint Name Input",                 "value": "{name}",  "description": "Ввести имя",               "timeout_ms": 3000},
            {"step_id": 6, "action_type": "shortcut",    "target": "Global",                               "value": "Return",  "description": "Подтвердить",              "timeout_ms": 2000},
            {"step_id": 7, "action_type": "shortcut",    "target": "Global",                               "value": "Ctrl+S",  "description": "Сохранить",                "timeout_ms": 3000},
        ]
    ),

    "create_material": WorkflowTemplate(
        name="create_material",
        description="Создать новый Material",
        tags=["create", "material", "shader"],
        estimated_duration_sec=6,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                        "value": "Ctrl+B",  "description": "Открыть Content Browser",   "timeout_ms": 2000},
            {"step_id": 2, "action_type": "right_click", "target": "Content Browser Empty Area",     "value": None,      "description": "Контекстное меню",          "timeout_ms": 3000},
            {"step_id": 3, "action_type": "click",       "target": "Context Menu > New Material",    "value": None,      "description": "Создать Material",          "timeout_ms": 4000},
            {"step_id": 4, "action_type": "type",        "target": "Blueprint Name Input",           "value": "{name}",  "description": "Ввести имя материала",      "timeout_ms": 3000},
            {"step_id": 5, "action_type": "shortcut",    "target": "Global",                         "value": "Return",  "description": "Подтвердить",              "timeout_ms": 2000},
        ]
    ),

    "create_widget": WorkflowTemplate(
        name="create_widget",
        description="Создать Widget Blueprint (UI элемент)",
        tags=["create", "widget", "ui", "hud"],
        estimated_duration_sec=8,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                             "value": "Ctrl+B",  "description": "Открыть Content Browser",   "timeout_ms": 2000},
            {"step_id": 2, "action_type": "right_click", "target": "Content Browser Empty Area",          "value": None,      "description": "Контекстное меню",          "timeout_ms": 3000},
            {"step_id": 3, "action_type": "click",       "target": "Context Menu > New Widget Blueprint", "value": None,      "description": "Создать Widget",            "timeout_ms": 4000},
            {"step_id": 4, "action_type": "type",        "target": "Blueprint Name Input",                "value": "{name}",  "description": "Ввести имя виджета",        "timeout_ms": 3000},
            {"step_id": 5, "action_type": "shortcut",    "target": "Global",                              "value": "Return",  "description": "Подтвердить",              "timeout_ms": 2000},
            {"step_id": 6, "action_type": "shortcut",    "target": "Global",                              "value": "Ctrl+S",  "description": "Сохранить",                "timeout_ms": 3000},
        ]
    ),

    "import_fbx": WorkflowTemplate(
        name="import_fbx",
        description="Импортировать FBX модель в Content Browser",
        tags=["import", "fbx", "mesh", "model"],
        estimated_duration_sec=15,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                   "value": "Ctrl+B",  "description": "Открыть Content Browser",   "timeout_ms": 2000},
            {"step_id": 2, "action_type": "click",       "target": "Content Browser Import Button", "value": None, "description": "Нажать Import",            "timeout_ms": 3000},
            {"step_id": 3, "action_type": "wait",        "target": "Global",                   "value": "2000",    "description": "Ждать диалог выбора файла", "timeout_ms": 5000},
            {"step_id": 4, "action_type": "wait",        "target": "Global",                   "value": "3000",    "description": "Ждать FBX Import Options",  "timeout_ms": 8000},
            {"step_id": 5, "action_type": "click",       "target": "Active Dialog OK Button",  "value": None,      "description": "Подтвердить импорт",        "timeout_ms": 5000},
            {"step_id": 6, "action_type": "shortcut",    "target": "Global",                   "value": "Ctrl+S",  "description": "Сохранить все",             "timeout_ms": 3000},
        ]
    ),

    "save_all": WorkflowTemplate(
        name="save_all",
        description="Сохранить все несохранённые ассеты",
        tags=["save", "project", "all"],
        estimated_duration_sec=5,
        steps=[
            {"step_id": 1, "action_type": "shortcut", "target": "Global", "value": "Ctrl+Shift+S", "description": "Сохранить всё",           "timeout_ms": 3000},
            {"step_id": 2, "action_type": "wait",     "target": "Global", "value": "1500",         "description": "Ждать диалог",            "timeout_ms": 5000},
            {"step_id": 3, "action_type": "click",    "target": "Active Dialog OK Button", "value": None, "description": "Подтвердить",       "timeout_ms": 5000},
        ]
    ),

    "play_in_editor": WorkflowTemplate(
        name="play_in_editor",
        description="Запустить игру в редакторе (PIE)",
        tags=["play", "run", "pie", "test"],
        estimated_duration_sec=3,
        steps=[
            {"step_id": 1, "action_type": "shortcut", "target": "Global", "value": "F5", "description": "Запустить PIE", "timeout_ms": 5000},
        ]
    ),

    "compile_all_blueprints": WorkflowTemplate(
        name="compile_all_blueprints",
        description="Компилировать все Blueprint файлы",
        tags=["compile", "blueprint", "build", "all"],
        estimated_duration_sec=30,
        steps=[
            {"step_id": 1, "action_type": "click",    "target": "Main Menu > Tools",              "value": None,   "description": "Открыть меню Tools",         "timeout_ms": 3000},
            {"step_id": 2, "action_type": "click",    "target": "Tools Menu > Compile Blueprints", "value": None,  "description": "Компилировать Blueprint",    "timeout_ms": 5000},
            {"step_id": 3, "action_type": "wait",     "target": "Global",                         "value": "5000", "description": "Ожидание компиляции",        "timeout_ms": 60000},
        ]
    ),

    "create_folder": WorkflowTemplate(
        name="create_folder",
        description="Создать новую папку в Content Browser",
        tags=["create", "folder", "directory"],
        estimated_duration_sec=5,
        steps=[
            {"step_id": 1, "action_type": "shortcut",    "target": "Global",                       "value": "Ctrl+B",  "description": "Открыть Content Browser",   "timeout_ms": 2000},
            {"step_id": 2, "action_type": "right_click", "target": "Content Browser Empty Area",   "value": None,      "description": "Контекстное меню",          "timeout_ms": 3000},
            {"step_id": 3, "action_type": "click",       "target": "Context Menu > New Folder",    "value": None,      "description": "Создать папку",             "timeout_ms": 3000},
            {"step_id": 4, "action_type": "type",        "target": "Folder Name Input",            "value": "{name}",  "description": "Ввести имя папки",          "timeout_ms": 3000},
            {"step_id": 5, "action_type": "shortcut",    "target": "Global",                       "value": "Return",  "description": "Подтвердить",              "timeout_ms": 2000},
        ]
    ),
}


def get_workflow_template(name: str) -> WorkflowTemplate | None:
    return BUILTIN_WORKFLOWS.get(name)


def find_templates_by_tags(tags: list[str]) -> list[WorkflowTemplate]:
    """Поиск шаблонов по тегам."""
    results = []
    tags_lower = [t.lower() for t in tags]
    for wf in BUILTIN_WORKFLOWS.values():
        if any(tag in wf.tags for tag in tags_lower):
            results.append(wf)
    return results


def resolve_template_vars(steps: list[dict], variables: dict) -> list[dict]:
    """
    Подставляет переменные в шаги шаблона.
    {name} → "PlayerCharacter" и т.д.
    """
    import copy, json
    steps_copy = copy.deepcopy(steps)
    steps_str = json.dumps(steps_copy)
    for key, value in variables.items():
        steps_str = steps_str.replace("{" + key + "}", str(value or ""))
    return json.loads(steps_str)
