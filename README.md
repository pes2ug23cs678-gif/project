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

This project implements an end-to-end **COBOL-to-Python code migration pipeline** with a built-in validation layer. It uses a modern hybrid LLM stack combined with a deterministic execution sandbox:

- **Router Agent** — SmolLM (135m via Ollama) routes tasks via complexity analysis or rule-based fallbacks.
- **Translation Expert** — Groq (llama-3.3-70b-versatile) translates COBOL constructs to idiomatic Python, guided by rigid field-width calculation and structural rules.
- **Debug Expert** — Groq operates alongside a deterministic, deterministic quick-fixer to automatically patch syntax and runtime errors iteratively.
- **Execution Sandbox** — A pure subprocess sandbox (no LLM, auto-stubs missing data files) safely evaluates generated code.

The system is augmented with **Retrieval-Augmented Generation (RAG)** for context-aware translation and features a **confidence-scoring engine** and a **research-grade evaluation framework** for comparative analysis.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    COBOL Source Code Input                      │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
               ┌───────────────────────┐
               │   1. Preprocessing    │  Normalize & chunk by procedure
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ 2. Structure Analysis │  Extract paragraphs & IO context
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   3. RAG Context      │  Retrieve relevant knowledge
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ 4. Route (SmolLM/Rule)│  Determine complexity
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ 5. Translate (Groq)   │  COBOL → Idiomatic Python
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ 6. Sandbox + Debug    │  Rule-based + Groq iteration
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   7. Validation       │  Calculate Confidence Score
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   Generated Python    │  Final output & Agents UI payload
               └───────────────────────┘
```

---

## Project Structure

```
project/
├── main.py                     # 7-step Pipeline entry point (CLI + API)
├── config.py                   # Centralized model & routing config
├── requirements.txt            # Python dependencies
├── abstract_introduction.md    # IEEE research paper drafting
│
├── agents/                     # Multi-agent system
│   ├── __init__.py
│   ├── agent_controller.py     # Orchestrates all agents
│   ├── router.py               # SmolLM routing & rule-based fallback
│   ├── structure_expert.py     # Legacy COBOL structure analysis
│   ├── translation_expert.py   # Groq COBOL → Python translation
│   ├── test_expert.py          # Test case generation
│   ├── debug_expert.py         # Groq code repair
│   ├── prompts.py              # Prompt templates
│   └── examples.py             # Few-shot examples
│
├── preprocessing/              # Input normalization
│   ├── __init__.py
│   └── preprocessor.py         # Chunking & base utils
│
├── rag/                        # Retrieval-Augmented Generation
│   ├── __init__.py
│   └── rag_engine.py           # Knowledge base ingestion
│
├── execution/                  # Code execution & validation
│   ├── __init__.py
│   ├── sandbox.py              # Secure subprocess sandbox (auto-stubs IO)
│   ├── debug_loop.py           # Per-iteration timed debug loop
│   ├── executor.py             # Legacy execution
│   └── validator.py            # Legacy validation
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

| Stage | Component | Description |
|-------|--------|-------------|
| **1. Preprocessing** | `preprocessing/preprocessor.py` | Normalizes COBOL source, chunks by procedure/paragraph |
| **2. Structured Analysis**| `main.py` | Extracts paragraphs and determines file I/O requirements |
| **3. RAG Context** | `main.py` / `rag` | Retrieves relevant domain/file knowledge from the knowledge base |
| **4. Routing** | `agents/router.py` | Classifies complexity using SmolLM via Ollama (or rule-based fallback) |
| **5. Translation** | `agents/translation_expert.py` | Main AST to Idiomatic Python translation via Groq (`llama-3.3-70b-versatile`) |
| **6. Execution + Debug**| `execution/debug_loop.py` & `sandbox.py` | Sandbox evaluation with quick iterative rule-based and LLM-assisted patching |
| **7. Validation** | `main.py` | Verifies success and assigns a holistic confidence score percentage |

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
