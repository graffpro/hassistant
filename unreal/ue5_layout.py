"""
Карта UI-элементов Unreal Engine 5.
Описывает расположение панелей и их семантику.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PanelInfo:
    """Описание панели/окна UE5."""
    semantic_name: str          # Как ссистент называет элемент
    ui_names: list[str]         # Варианты названий в UE5 UI
    default_position: str       # "left" | "right" | "bottom" | "top" | "center" | "floating"
    can_be_docked: bool = True
    keyboard_shortcut: str = ""
    description: str = ""
    child_elements: list[str] = field(default_factory=list)


UE5_PANELS: dict[str, PanelInfo] = {
    "Content Browser": PanelInfo(
        semantic_name="Content Browser",
        ui_names=["Content Browser", "Content Browser 1", "Content"],
        default_position="bottom",
        keyboard_shortcut="Ctrl+B",
        description="Менеджер ассетов проекта",
        child_elements=[
            "Content Browser Search Bar",
            "Content Browser Empty Area",
            "Content Browser Asset List",
            "Content Browser Folder Tree",
            "Content Browser Filters",
        ]
    ),
    "World Outliner": PanelInfo(
        semantic_name="World Outliner",
        ui_names=["World Outliner", "Outliner"],
        default_position="right",
        description="Список всех акторов на уровне",
        child_elements=["World Outliner Search", "World Outliner Actor List"]
    ),
    "Details Panel": PanelInfo(
        semantic_name="Details Panel",
        ui_names=["Details"],
        default_position="right",
        description="Свойства выбранного актора/ассета",
    ),
    "Viewport": PanelInfo(
        semantic_name="Viewport",
        ui_names=["Perspective", "Viewport", "Level Editor Viewport"],
        default_position="center",
        description="3D вид сцены",
        child_elements=["Toolbar Play Button", "Viewport Camera", "Viewport Gizmo"]
    ),
    "Blueprint Editor": PanelInfo(
        semantic_name="Blueprint Editor",
        ui_names=["Event Graph", "Blueprint Editor", "Graph"],
        default_position="floating",
        description="Редактор Blueprint графов",
        child_elements=[
            "Blueprint Graph Area",
            "Blueprint Components Panel",
            "Blueprint My Blueprint Panel",
            "Blueprint Details Panel",
            "Blueprint Toolbar Compile Button",
        ]
    ),
    "Material Editor": PanelInfo(
        semantic_name="Material Editor",
        ui_names=["Material Editor", "Material Graph"],
        default_position="floating",
        description="Редактор материалов",
    ),
    "Output Log": PanelInfo(
        semantic_name="Output Log",
        ui_names=["Output Log", "Log"],
        default_position="bottom",
        description="Лог ошибок и вывода",
    ),
    "Toolbar": PanelInfo(
        semantic_name="Toolbar",
        ui_names=["Toolbar", "Level Editor Toolbar"],
        default_position="top",
        can_be_docked=False,
        description="Главная панель инструментов",
        child_elements=[
            "Toolbar Play Button",
            "Toolbar Build Button",
            "Toolbar Source Control Button",
            "Toolbar Settings Button",
        ]
    ),
    "Main Menu": PanelInfo(
        semantic_name="Main Menu",
        ui_names=["File", "Edit", "Window", "Tools", "Help"],
        default_position="top",
        can_be_docked=False,
        description="Главное меню",
        child_elements=[
            "Main Menu > File",
            "Main Menu > Edit",
            "Main Menu > Window",
            "Main Menu > Tools",
        ]
    ),
}


# Контекстные меню — что появляется при правом клике
CONTEXT_MENUS: dict[str, list[str]] = {
    "Content Browser Empty Area": [
        "Context Menu > New Blueprint Class",
        "Context Menu > New Material",
        "Context Menu > New Folder",
        "Context Menu > Import",
        "Context Menu > New Widget Blueprint",
        "Context Menu > New Level",
        "Context Menu > New Niagara System",
        "Context Menu > New Data Table",
        "Context Menu > New Sound Wave",
    ],
    "Content Browser Asset": [
        "Context Menu > Open",
        "Context Menu > Edit",
        "Context Menu > Rename",
        "Context Menu > Duplicate",
        "Context Menu > Delete",
        "Context Menu > Save",
        "Context Menu > Show in Explorer",
        "Context Menu > Reference Viewer",
    ],
    "World Outliner Actor": [
        "Context Menu > Edit",
        "Context Menu > Rename",
        "Context Menu > Delete",
        "Context Menu > Duplicate",
        "Context Menu > Select All",
        "Context Menu > Focus Viewport",
    ],
    "Viewport Actor": [
        "Context Menu > Edit",
        "Context Menu > Select",
        "Context Menu > Snap to Floor",
        "Context Menu > Group",
    ],
}


def get_panel(semantic_name: str) -> Optional[PanelInfo]:
    return UE5_PANELS.get(semantic_name)


def find_panel_by_ui_name(ui_name: str) -> Optional[PanelInfo]:
    for panel in UE5_PANELS.values():
        if any(ui_name.lower() in n.lower() for n in panel.ui_names):
            return panel
    return None


def get_context_menu_items(target: str) -> list[str]:
    return CONTEXT_MENUS.get(target, [])
