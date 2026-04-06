# 🔄 COBOL → Python Migration Pipeline

An AI-powered, multi-agent system that automatically migrates legacy COBOL programs to Python — with RAG-augmented context retrieval, self-debugging, and a research-grade evaluation framework.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Usage](#usage)
  - [CLI Pipeline](#1-cli-pipeline)
  - [Streamlit UI](#2-streamlit-ui)
  - [Evaluation Framework](#3-evaluation-framework)
  - [RAG Ingestion](#4-rag-knowledge-base-ingestion)
  - [Programmatic API](#5-programmatic-api)
- [Pipeline Stages](#pipeline-stages)
- [Evaluation](#evaluation)
- [Team](#team)

---

## Overview

This project implements an end-to-end **COBOL-to-Python code migration pipeline** with a built-in validation layer. It uses a multi-agent architecture where specialized AI agents handle different aspects of the translation:

- **Router Agent** — classifies task complexity and determines the optimal processing flow
- **Structure Expert** — parses COBOL divisions, sections, and data items
- **Translation Expert** — converts COBOL constructs to idiomatic Python
- **Test Expert** — generates test cases for the translated code
- **Debug Expert** — iteratively fixes errors via a self-debugging loop

The system is augmented with **Retrieval-Augmented Generation (RAG)** for context-aware translation and includes a **research-grade evaluation framework** for comparative analysis.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    COBOL Source Code Input                       │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
               ┌───────────────────────┐
               │   1. Preprocessing    │  Normalize & chunk by procedure
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   2. RAG Context      │  Retrieve relevant knowledge
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   3. Agent Pipeline   │  Route → Structure → Translate → Test
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   4. Execution &      │  Sandbox run + self-debugging loop
               │      Debug Loop       │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   5. Validation       │  Output correctness & confidence
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   Generated Python    │  Final validated output
               └───────────────────────┘
```

---

## Project Structure

```
project/
├── main.py                     # Pipeline entry point (CLI + API)
├── config.py                   # Centralized config, enums, constants
├── requirements.txt            # Python dependencies
│
├── agents/                     # Multi-agent system
│   ├── __init__.py
│   ├── agent_controller.py     # Orchestrates all agents
│   ├── base.py                 # Abstract base class for experts
│   ├── router.py               # Complexity classification & routing
│   ├── structure_expert.py     # COBOL structure analysis
│   ├── translation_expert.py   # COBOL → Python translation
│   ├── test_expert.py          # Test case generation
│   ├── debug_expert.py         # Self-debugging agent
│   ├── prompts.py              # Prompt templates
│   └── examples.py             # Few-shot examples
│
├── preprocessing/              # Input normalization
│   ├── __init__.py
│   └── preprocessor.py         # Chunking & knowledge base utils
│
├── rag/                        # Retrieval-Augmented Generation
│   ├── __init__.py
│   └── rag_engine.py           # Knowledge base ingestion
│
├── execution/                  # Code execution & validation
│   ├── __init__.py
│   ├── executor.py             # Sandboxed Python execution
│   ├── validator.py            # Output validation & confidence
│   ├── debug_loop.py           # Iterative self-debugging
│   └── test_execution.py       # Execution tests
│
├── evaluation/                 # Research evaluation framework
│   ├── __init__.py
│   ├── evaluator.py            # Multi-system comparative evaluator
│   ├── correctness.py          # Output matching & scoring
│   ├── visualizer.py           # Basic visualization
│   ├── visualizer_research.py  # Publication-ready charts
│   ├── test_cases.json         # Evaluation test suite
│   └── plots/                  # Generated comparison charts
│
├── ui/                         # Web interface
│   ├── __init__.py
│   └── app.py                  # Streamlit dashboard
│
└── data/                       # Data files
    └── knowledge_base/         # RAG knowledge store
```

---

## Setup

### Prerequisites

- **Python 3.10+** (tested with Python 3.13)
- **pip** (Python package manager)

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/pes2ug23cs678-gif/project.git
   cd project
   ```

2. **Create a virtual environment** (recommended)

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Linux / macOS
   # .venv\Scripts\activate         # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

### 1. CLI Pipeline

Run the interactive command-line interface:

```bash
python main.py
```

This presents a menu with three options:
- **Paste** COBOL source interactively
- **Load** from a `.cob` / `.cbl` file
- **Run** a built-in sample (PAYROLL program)

**Translate from a file directly:**

```bash
python main.py --file path/to/source.cob
```

---

### 2. Streamlit UI

Launch the interactive web dashboard:

```bash
streamlit run ui/app.py
```

The UI provides:
- COBOL input via paste, file upload, or built-in sample
- Real-time pipeline execution with progress tracking
- Tabbed output: generated Python code, logs, timing breakdown, validation report, and full agent analysis
- Downloadable `.py` output

---

### 3. Evaluation Framework

Run the full research evaluation (compares Baseline LLM vs RAG-Only vs Full Agentic RAG):

```bash
# Full comparison with charts
python -m evaluation.evaluator --plots

# With ablation study
python -m evaluation.evaluator --plots --ablation

# Custom test file + output path
python -m evaluation.evaluator --file path/to/tests.json --report results.json

# Quiet mode (suppress per-test output)
python -m evaluation.evaluator --plots --ablation --quiet
```

**Evaluator CLI flags:**

| Flag | Description |
|------|-------------|
| `--file`, `-f` | Path to a custom `test_cases.json` |
| `--report`, `-r` | Output path for JSON results (default: `evaluation_results.json`) |
| `--plots`, `-p` | Generate publication-ready comparison charts |
| `--plot-dir` | Chart output directory (default: `evaluation/plots`) |
| `--ablation`, `-a` | Run ablation study (RAG vs Debug contributions) |
| `--quiet`, `-q` | Suppress per-test console output |

---

### 4. RAG Knowledge Base Ingestion

Ingest COBOL source files into the knowledge base for RAG-augmented translation:

```bash
python -m rag.rag_engine
```

Place your COBOL files in the `data/` directory and update the file paths in `rag/rag_engine.py`.

---

### 5. Programmatic API

Use the pipeline in your own Python code:

```python
from main import run_pipeline

cobol_source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'Hello, World!'.
           STOP RUN.
"""

result = run_pipeline(cobol_source)

print(result["python_code"])       # Generated Python
print(result["result"]["status"])  # SUCCESS / PARTIAL / FAILED
print(result["result"]["confidence_score"])  # 0-100
```

---

## Pipeline Stages

| Stage | Module | Description |
|-------|--------|-------------|
| **Preprocessing** | `preprocessing/preprocessor.py` | Normalizes COBOL source, chunks by procedure/paragraph |
| **RAG Context** | `rag/rag_engine.py` | Retrieves relevant context from the knowledge base |
| **Routing** | `agents/router.py` | Classifies complexity (simple/complex), determines agent flow |
| **Structure Analysis** | `agents/structure_expert.py` | Parses COBOL divisions, data items, paragraphs |
| **Translation** | `agents/translation_expert.py` | Converts COBOL → Python with construct mapping |
| **Test Generation** | `agents/test_expert.py` | Generates test cases (happy path, boundary, error) |
| **Execution** | `execution/executor.py` | Runs generated Python in a sandboxed subprocess |
| **Debug Loop** | `execution/debug_loop.py` | Iteratively fixes errors (up to N retries) |
| **Validation** | `execution/validator.py` | Verifies output correctness, assigns confidence score |

---

## Evaluation

The evaluation framework compares three system configurations:

| System | RAG | Debug Loop | Description |
|--------|-----|------------|-------------|
| **Baseline LLM** | ✗ | ✗ | Direct single-pass translation |
| **RAG-Only** | ✓ | ✗ | Retrieval-augmented, no self-debugging |
| **Full Agentic RAG** | ✓ | ✓ | Full pipeline with self-debugging |

**Metrics computed:**
- Test pass rate, execution success rate
- Average debug iterations, execution time
- Failure detection rate, silent error rate
- Confidence score distribution
- Per-category and per-difficulty breakdowns

Generated charts are saved to `evaluation/plots/`.

---

## Team

**PES University — GenAI Mini Project**

---
