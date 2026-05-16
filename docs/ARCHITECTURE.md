# UE5 AI Assistant — Architecture Document

## Overview

A production-grade autonomous AI assistant that observes, understands, and acts within Unreal Engine 5. The user interacts via a persistent floating UI (text or voice), and the assistant autonomously executes tasks inside UE5.

---

## Execution Pipeline

```
User Input (Text/Voice)
        │
        ▼
[UI Layer] ──────────────────────────────────────────┐
  Floating overlay, chat, mic input                  │
        │                                             │
        ▼                                             │
[Core Orchestrator]                                   │
  Parses intent, plans steps, dispatches agents       │
        │                                             │
        ├──────────────────────────────────────────   │
        │              │              │               │
        ▼              ▼              ▼               │
   [Brain]        [Memory]        [Vision]            │
   LLM via        SQLite +        Screenshot +        │
   Ollama         ChromaDB        OCR + CV            │
   Intent         Workflows       UI Detection        │
   Planning       User habits     Panel recognition   │
        │              │              │               │
        └──────┬────────┘              │               │
               │                      │               │
               ▼                      │               │
        [Automation]  ◄───────────────┘               │
        PyAutoGUI +                                    │
        Win32 API +                                    │
        UIA (UI Automation)                            │
               │                                      │
               ▼                                      │
        [Safety Guard]                                │
        Validates actions,                            │
        asks confirmation                             │
        for dangerous ops                             │
               │                                      │
               ▼                                      │
        [Unreal Engine 5] ◄──────────────────────────┘
        Content Browser, Blueprint Editor,
        World Outliner, Details Panel, etc.
               │
               ▼
        [Learning Module]
        Detects patterns,
        builds reusable workflows,
        updates memory
```

---

## Module Responsibilities

### `core/` — Orchestrator
- `orchestrator.py` — Main loop, dispatches tasks to modules
- `event_bus.py` — Internal pub/sub event system
- `config.py` — Global settings and paths
- `logger.py` — Structured logging

### `ui/` — Floating Overlay
- `overlay.py` — Always-on-top floating window (PyQt6)
- `chat_widget.py` — Text input/output chat interface
- `voice_input.py` — Microphone capture + Whisper STT
- `status_bar.py` — Live status: thinking / executing / idle
- `tray_icon.py` — System tray icon

### `brain/` — AI Reasoning
- `llm_client.py` — Ollama API client (Qwen/Llama3/DeepSeek)
- `intent_parser.py` — Extracts intent + entities from user input
- `task_planner.py` — Breaks intent into executable step sequence
- `context_manager.py` — Maintains conversation context

### `vision/` — Screen Understanding
- `screen_capture.py` — Continuous screenshot capture
- `ui_detector.py` — Detects UE5 panels via CV + template matching
- `ocr_engine.py` — Tesseract OCR for reading UI text
- `semantic_mapper.py` — Maps visual elements to semantic labels

### `automation/` — Action Execution
- `mouse_controller.py` — Semantic mouse actions (not raw coords)
- `keyboard_controller.py` — Text input, shortcuts
- `window_manager.py` — Win32 window focus/management
- `uia_controller.py` — Windows UI Automation for robust clicking
- `action_executor.py` — High-level action dispatcher

### `memory/` — Long-Term Memory
- `workflow_store.py` — SQLite: stores named reusable workflows
- `experience_store.py` — SQLite: success/failure history
- `vector_store.py` — ChromaDB: semantic search over workflows
- `user_profile.py` — User habits, preferences, project context
- `memory_manager.py` — Unified memory interface

### `learning/` — Passive Learning
- `observer.py` — Mouse/keyboard observation (pynput)
- `pattern_detector.py` — Detects repeated action sequences
- `workflow_builder.py` — Converts patterns to reusable workflows
- `intent_inferrer.py` — Infers semantic intent from raw actions

### `safety/` — Safety System
- `action_validator.py` — Validates actions before execution
- `confirmation_dialog.py` — Asks user to confirm dangerous ops
- `backup_manager.py` — Creates project snapshots before risky ops
- `rollback_manager.py` — Reverts changes if action fails

### `unreal/` — UE5 Knowledge
- `ue5_layout.py` — Known panel positions and identifiers
- `ue5_shortcuts.py` — UE5 keyboard shortcuts map
- `ue5_workflows.py` — Built-in common UE5 task templates
- `asset_types.py` — Blueprint, Material, Actor, etc. definitions

---

## Data Flow — User Command Example

**User says:** *"Create a Blueprint Actor named PlayerCharacter in Characters folder"*

```
1. voice_input.py       → captures audio
2. Whisper STT          → "Create a Blueprint Actor named PlayerCharacter in Characters folder"
3. intent_parser.py     → { action: "create_asset", type: "Blueprint", name: "PlayerCharacter", folder: "Characters" }
4. memory_manager.py    → searches for existing workflow "create_blueprint_actor"
5. task_planner.py      → steps: [open_content_browser, navigate_to_folder, right_click, new_blueprint, set_name, save]
6. safety/validator     → validates: no destructive action → proceed
7. action_executor.py   → executes each step
8. vision/ui_detector   → validates each step visually after execution
9. learning/observer    → records successful workflow
10. memory_manager.py   → stores workflow for future reuse
11. ui/overlay.py       → reports: "✅ PlayerCharacter Blueprint created in Characters/"
```

---

## Memory Architecture

```
SQLite Database (local)
├── workflows          — name, steps (JSON), success_count, last_used
├── experiences        — action, result, context, timestamp
├── user_habits        — repeated patterns, preferences
└── project_context    — current UE5 project info

ChromaDB (vector search)
└── workflow_embeddings — semantic search: "create asset" → finds all creation workflows
```

---

## Tech Stack

| Layer        | Technology                          |
|--------------|-------------------------------------|
| Language     | Python 3.11+                        |
| UI           | PyQt6                               |
| Local LLM    | Ollama (Qwen2.5 / Llama3 / DeepSeek)|
| STT          | OpenAI Whisper (local)              |
| Vision       | OpenCV + Tesseract OCR              |
| Automation   | PyAutoGUI + pywin32 + comtypes (UIA)|
| Memory       | SQLite + ChromaDB                   |
| Packaging    | PyInstaller                         |

---

## MVP Phases

### Phase 1 — Skeleton (Week 1)
- Floating UI overlay with text chat
- Ollama LLM integration
- Basic intent parsing
- Manual action execution (simple UE5 tasks)

### Phase 2 — Vision (Week 2)
- Screenshot capture
- UE5 panel detection
- OCR for reading UI
- Semantic element mapping

### Phase 3 — Memory (Week 3)
- SQLite workflow storage
- ChromaDB vector search
- Experience logging

### Phase 4 — Learning (Week 4)
- Passive observation (pynput)
- Pattern detection
- Workflow auto-building

### Phase 5 — Voice + Safety (Week 5)
- Whisper voice input
- Safety validation
- Confirmation dialogs
- Backup/rollback

### Phase 6 — Polish + Packaging (Week 6)
- Error recovery
- UI polish
- PyInstaller packaging
- Documentation
