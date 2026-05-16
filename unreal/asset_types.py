"""
Типы ассетов и объектов в Unreal Engine 5.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AssetType:
    name: str                        # Внутреннее имя
    display_name: str                # Отображаемое имя
    icon: str                        # Иконка (эмодзи для UI)
    extensions: list[str]            # Расширения файлов
    parent_classes: list[str]        # Допустимые родительские классы
    content_browser_path: str        # Путь в меню создания
    description: str = ""


ASSET_TYPES: dict[str, AssetType] = {
    "Blueprint": AssetType(
        name="Blueprint",
        display_name="Blueprint Class",
        icon="🔷",
        extensions=[".uasset"],
        parent_classes=["Actor", "Character", "Pawn", "GameMode",
                        "PlayerController", "ActorComponent", "GameInstance",
                        "UserWidget", "AnimInstance"],
        content_browser_path="Blueprint Class",
        description="Визуальный скриптинг — основа геймплея в UE5",
    ),
    "Material": AssetType(
        name="Material",
        display_name="Material",
        icon="🎨",
        extensions=[".uasset"],
        parent_classes=[],
        content_browser_path="Material",
        description="Шейдер/материал для объектов",
    ),
    "MaterialInstance": AssetType(
        name="MaterialInstance",
        display_name="Material Instance",
        icon="🖌️",
        extensions=[".uasset"],
        parent_classes=[],
        content_browser_path="Material Instance (Constant)",
        description="Экземпляр материала с настраиваемыми параметрами",
    ),
    "StaticMesh": AssetType(
        name="StaticMesh",
        display_name="Static Mesh",
        icon="📦",
        extensions=[".uasset", ".fbx", ".obj", ".gltf"],
        parent_classes=[],
        content_browser_path="Static Mesh",
        description="Статичная 3D-модель",
    ),
    "SkeletalMesh": AssetType(
        name="SkeletalMesh",
        display_name="Skeletal Mesh",
        icon="🦴",
        extensions=[".uasset", ".fbx"],
        parent_classes=[],
        content_browser_path="Skeletal Mesh",
        description="Анимируемая 3D-модель со скелетом",
    ),
    "Texture": AssetType(
        name="Texture",
        display_name="Texture 2D",
        icon="🖼️",
        extensions=[".uasset", ".png", ".jpg", ".tga", ".exr"],
        parent_classes=[],
        content_browser_path="Texture 2D",
        description="Текстура/изображение",
    ),
    "Sound": AssetType(
        name="Sound",
        display_name="Sound Wave",
        icon="🔊",
        extensions=[".uasset", ".wav", ".mp3", ".ogg"],
        parent_classes=[],
        content_browser_path="Sound Wave",
        description="Звуковой файл",
    ),
    "Widget": AssetType(
        name="Widget",
        display_name="Widget Blueprint",
        icon="🖥️",
        extensions=[".uasset"],
        parent_classes=["UserWidget"],
        content_browser_path="Widget Blueprint",
        description="UI виджет (HUD, меню)",
    ),
    "Animation": AssetType(
        name="Animation",
        display_name="Animation Sequence",
        icon="🎬",
        extensions=[".uasset", ".fbx"],
        parent_classes=[],
        content_browser_path="Animation Sequence",
        description="Анимационная последовательность",
    ),
    "ParticleSystem": AssetType(
        name="ParticleSystem",
        display_name="Niagara System",
        icon="✨",
        extensions=[".uasset"],
        parent_classes=[],
        content_browser_path="Niagara System",
        description="Система частиц (Niagara)",
    ),
    "DataTable": AssetType(
        name="DataTable",
        display_name="Data Table",
        icon="📊",
        extensions=[".uasset", ".csv"],
        parent_classes=[],
        content_browser_path="Data Table",
        description="Таблица данных для геймплея",
    ),
    "Level": AssetType(
        name="Level",
        display_name="Level",
        icon="🗺️",
        extensions=[".umap"],
        parent_classes=[],
        content_browser_path="Level",
        description="Уровень/карта",
    ),
    "Folder": AssetType(
        name="Folder",
        display_name="Folder",
        icon="📁",
        extensions=[],
        parent_classes=[],
        content_browser_path="New Folder",
        description="Папка в Content Browser",
    ),
}


def get_asset_type(name: str) -> Optional[AssetType]:
    """Возвращает тип ассета по имени (регистронезависимо)."""
    name_lower = name.lower()
    for key, asset in ASSET_TYPES.items():
        if key.lower() == name_lower or asset.display_name.lower() == name_lower:
            return asset
    return None


def get_parent_classes(asset_type: str) -> list[str]:
    asset = get_asset_type(asset_type)
    return asset.parent_classes if asset else ["Actor"]


# Синонимы для парсера намерений
ASSET_SYNONYMS: dict[str, str] = {
    "блюпринт": "Blueprint",
    "blueprint": "Blueprint",
    "bp": "Blueprint",
    "материал": "Material",
    "material": "Material",
    "мат": "Material",
    "меш": "StaticMesh",
    "mesh": "StaticMesh",
    "модель": "StaticMesh",
    "текстура": "Texture",
    "texture": "Texture",
    "звук": "Sound",
    "sound": "Sound",
    "виджет": "Widget",
    "widget": "Widget",
    "анимация": "Animation",
    "animation": "Animation",
    "уровень": "Level",
    "level": "Level",
    "карта": "Level",
    "папка": "Folder",
    "folder": "Folder",
    "частицы": "ParticleSystem",
    "niagara": "ParticleSystem",
}


def resolve_asset_type(raw: str) -> str:
    """Нормализует название типа ассета."""
    return ASSET_SYNONYMS.get(raw.lower(), raw)
