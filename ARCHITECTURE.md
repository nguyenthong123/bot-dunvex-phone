# OpenClaw Android: Comprehensive Architectural Blueprint

This document provides a visual and technical map of the OpenClaw bot system running on Android (Termux). It is designed to help you understand the data flow and identify where errors typically arise.

## 1. Overall System Architecture
This diagram shows how your messages travel through the different "organs" of the bot's brain.

```mermaid
graph TD
    %% User Interface
    User((User on Telegram)) -- Message --> TG[Telegram Bot API]
    TG -- Update --> Bot[bot.py: Python Application]

    %% Orchestration Layer
    subgraph "Android Termux (Managed by PM2)"
        Bot -- user_text --> Orchestrator["StreamingOrchestrator (core/streaming_ai.py)"]
        Orchestrator -- Request --> DS["DeepSeek-R1 (Reasoning Cloud)"]
        DS -- Streamed Chunks --> Orchestrator
        
        %% Local Analysis
        Orchestrator -- Analysis Request --> LocalCoder["Local Analysis (Llama 3.2 1B)"]
        LocalCoder -- Context --> Orchestrator
        
        %% Tool Execution
        Orchestrator -- Tool Call --> ToolManager[Tool Gateway]
        subgraph "Tool Execution Layer"
            ToolManager -- Write/Read --> FS[Local Filesystem]
            ToolManager -- MCP/Shell --> GitHub[GitHub Actions / Git]
        end
    end

    %% Feedback Loop
    Orchestrator -- HTML Status --> TG
    Orchestrator -- Final Answer --> TG
    TG -- Notification --> User
```

## 2. Risk & Failure Points Map
This diagram highlights the 4 critical points where the bot used to "break" and how we fixed them.

```mermaid
graph LR
    A[Point 1: Connection] --> B[Point 2: Parsing]
    B --> C[Point 3: OS Killing]
    C --> D[Point 4: Formatting]

    subgraph "Failure Modes"
        A["<b>1. API Timeout</b><br/>Status: 0-byte writes<br/>Fix: 600s Extended Timeout"]
        B["<b>2. Parser Fail</b><br/>Status: Truncated code<br/>Fix: Graceful Balanced Parser"]
        C["<b>3. Android PPK</b><br/>Status: Silent Bot Death<br/>Fix: PM2 Daemonization"]
        D["<b>4. Markdown Bug</b><br/>Status: TG 400 Error<br/>Fix: HTML Escape Mode"]
    end
```

## 3. Core Component Catalog

| File / Component | Responsibility | Intelligence Level |
| :--- | :--- | :--- |
| **`bot.py`** | Handles Telegram connectivity, polling, and HTML UI updates. | High (Interface) |
| **`streaming_ai.py`** | The "Maestro". Extracts tools from DeepSeek streams. | Max (Logic) |
| **`ollama_manager.py`**| Manages Llama 3.2 1B for heavy local code analysis. | Medium (Worker) |
| **`tools.py`** | Directly interacts with the Android filesystem. | Low (Worker) |
| **`mcp_manager.py`** | Bridges with GitHub and external servers. | Medium (Gateway) |
| **`memory.db`** | SQLite database storing all chat history. | Persistent (Storage) |

## 4. Troubleshooting Guide
When an error occurs, check this sequence:
1. **Connectivity**: Check `pm2 logs`. If `getUpdates` is 200, the network is OK.
2. **Brain**: If Bot is thinking but not writing, check the parser logic in `streaming_ai.py`.
3. **Storage**: Check `memory.db` for the last message ID to see if the bot "hallucinated" a success.

---
*Created by Antigravity AI Advisor - 2026-04-18*
