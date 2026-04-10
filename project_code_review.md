# Project Code Review: COBOL → Python Agentic RAG Migration Pipeline

---

## 1. Project Overview

| Field | Details |
|---|---|
| **Objective** | Automate the migration of legacy COBOL programs into idiomatic, executable Python code |
| **Approach** | Multi-agent LLM pipeline with Retrieval-Augmented Generation and iterative self-debugging |
| **Stack** | Python 3.10+, Groq API (llama-3.3-70b-versatile), SmolLM via Ollama, Streamlit |
| **Key Pattern** | Generate → Execute → Detect → Fix → Repeat (closed feedback loop) |
| **Evaluation** | 12 test cases across arithmetic / conditional / loop / nested categories, 3 system tiers |

---

## 2. Architecture Summary

```
COBOL Source
    │
    ▼
[1] Preprocessor (chunk_by_procedure)
    │   → Regex-based split on paragraph headers
    ▼
[2] Structure Analysis (_step_build_analysis)
    │   → Rule-based: extract paragraphs, detect IO, OCCURS, REDEFINES flags
    ▼
[3] RAG Context (_step_rag_context)
    │   → Reads knowledge base (.txt files), injects chunk previews
    ▼
[4] Router (SmolLM via Ollama → _rule_based fallback)
    │   → Classifies: "simple" or "complex"
    ▼
[5] Translation Expert (Groq llama-3.3-70b-versatile)
    │   → Prompt-guided COBOL → Python with 23+ explicit rules
    ▼
[6] Sandbox + Debug Loop (subprocess + rule-based patches + Groq escalation)
    │   → Max 7 iterations, 5s timeout first run / 3s retries
    ▼
[7] Validation Gate (sandbox_execute final check)
    │   → returncode == 0 && no stderr → PASS
    ▼
Output dict { python_code, logs, result, timing, agents }
    │
    ▼
Streamlit UI (5 tabs: Code | Logs | Timing | Validation | Agents)
```

**Agent Roles:**
| Agent | Model | Role |
|---|---|---|
| Structure Analyst | Rule-based | Paragraph/IO/flag detection |
| SLM Router | SmolLM:135m | Complexity classification |
| Translation Engine | Groq llama-3.3-70b | COBOL → Python conversion |
| Debug Expert | Groq llama-3.3-70b + rules | Error correction loop |
| Validator | Rule-based (subprocess) | Final pass/fail gate |

---

## 3. Key Strengths

**✅ Clean, Modular Architecture**
The pipeline is separated into clearly-named step functions (`_step_preprocess`, `_step_translate`, etc.), making it easy to test, replace, or disable individual stages independently.

**✅ Deterministic Quick-Fixes Before Expensive LLM Calls**
The `_quick_fix()` function in `debug_loop.py` handles the most common LLM mistakes (figurative constants, `=` vs `==`, missing imports) with zero-cost regex before ever touching the Groq API.

**✅ Sandbox Isolation**
The sandbox never uses `exec()` or `eval()`. It writes code to a `tempfile`, runs it as a subprocess with a strict timeout, and auto-stubs required data files via regex. This is genuinely safe and production-thinking.

**✅ Stale-Fix Detector**
If the LLM returns code identical to what it received, the loop terminates immediately (`fixed_code.strip() == current_code.strip()`). This prevents infinite burn of API tokens.

**✅ Dual-Timeout Strategy**
First sandbox run gets 5s (full budget), retries get 3s (fail-fast). This is solid engineering — it avoids wasting time on likely-infinite-loop code in later iterations.

**✅ Comprehensive Translation Prompt**
The `TRANSLATION_PROMPT` covers 23+ explicit rules for: operators, figurative constants, data types, OCCURS, PERFORM, EVALUATE, READ/WRITE, STRING, MOVE, REDEFINES, file handles, fixed-width parsing, global state, and a pre-emit checklist. This level of specificity is exceptional.

**✅ Research-Grade Evaluation Framework**
The `evaluation/evaluator.py` runs three systems (Baseline / RAG-Only / Full Agentic RAG), computes 8 metrics per system, performs ablation studies, and generates charts. It's a proper comparative framework.

**✅ Per-Agent Metadata UI**
The Streamlit "Agents" tab shows each expert's model, status, decisions, and iteration log — this is clean observability for a multi-agent system.

---

## 4. Limitations

### 4.1 Technical Limitations

#### ❌ L1: The RAG Is Essentially a No-Op
**Where:** `main.py` → `_step_rag_context()`, `data/knowledge_base/`  
**Why it's a limitation:** The knowledge base folder contains only a `.gitkeep` file. The RAG step reads chunk previews (first 120 chars) and any `.txt` files in the KB folder, but injects them as plain strings into a `context` dict that is never actually passed to the Translation Expert. The translation prompt doesn't receive this context.  
**Impact:** The "RAG" label in your system is misleading — translation runs without any retrieved context. The comparative advantage attributed to RAG in evaluation results is entirely simulated by probability degradation in `_run_rag_only()` and `_run_baseline()`, not real retrieval differences.

#### ❌ L2: pass_rate Is Binary (0 or 100) — Not Real Testing
**Where:** `main.py` → `_step_validate()`, lines 248–249  
**Why it's a limitation:**
```python
passed = result["returncode"] == 0 and not result["stderr"].strip()
pass_rate = 100 if passed else 0
```
Validation only checks if the script ran without crashing. It does **not** compare actual output against expected output. A program that prints `HELLO WRONG` when `HELLO WORLD` is expected would get a 100% pass rate.

#### ❌ L3: Baseline and RAG-Only Evaluations Are Simulated (Statistically Faked)
**Where:** `evaluation/evaluator.py` → `_run_baseline()` and `_run_rag_only()`  
**Why it's a limitation:** Both "comparison" systems run the **exact same full pipeline**, then apply random degradations using `random.Random(seed)` with hardcoded probability thresholds. This means your evaluation figures are not real measurements — the "Baseline LLM" in your charts is not a direct LLM call without RAG; it's your full pipeline plus artificial failures.  
**Academic risk:** If submitted to a conference, reviewers will question why Baseline and RAG-Only weren't independently implemented.

#### ❌ L4: Structure Expert Class Is Entirely Unused in the Pipeline
**Where:** `agents/structure_expert.py` → `StructureExpert` class  
**Why it's a limitation:** The full `StructureExpert` class (with `DataItem`, `ParagraphDetail`, regex-based parsers, hierarchy builder) is never imported or called in `main.py`. The pipeline uses an inline `_step_build_analysis()` which is a simplified duplicate. The rich `StructureExpert` is dead code.

#### ❌ L5: `config.py` Has Stale DeepSeek Aliases as Live Names
**Where:** `config.py` lines 13–17; `main.py` docstring lines 4–7  
**Why it's a limitation:** The module docstring in `main.py` still says "Translation Expert → DeepSeek V3" and log lines print "DeepSeek V3" but the actual model is Groq's llama. This creates confusion about what's actually running and could mislead someone debugging the system.

#### ❌ L6: `max_retries` Sidebar Slider in UI Does Nothing
**Where:** `ui/app.py` line 96  
**Why it's a limitation:**
```python
max_retries = st.slider("Debug retries", 1, 5, 3)
```
This slider is rendered in the sidebar but `run_pipeline()` always uses `SANDBOX_MAX_ITER` from `config.py` (hardcoded to 7). The slider value is never passed to the pipeline.

---

### 4.2 Data-Related Limitations

#### ❌ L7: Empty Knowledge Base — RAG Cannot Function
**Where:** `data/knowledge_base/` (contains only `.gitkeep`)  
**Why it's a limitation:** Without any ingested COBOL patterns, documentation, or translation examples in the KB, the RAG context retrieval step returns only chunk previews. The full power of RAG (retrieving contextually relevant mappings from a vector store) is absent.

#### ❌ L8: Test Suite Is Small and Narrow (12 Cases)
**Where:** `evaluation/test_cases.json`  
**Why it's a limitation:** 12 test cases across 4 categories cannot reliably measure system performance statistically. There are no tests for: file I/O programs, OCCURS tables, REDEFINES, COMP-3 decimal operations, or GO TO flows — precisely the hard cases the architecture was designed for.

---

### 4.3 Performance Limitations

#### ❌ L9: No Async Execution — Pipeline Is Fully Blocking
**Where:** `main.py` → `run_pipeline()`, `ui/app.py` → button handler  
**Why it's a limitation:** The entire pipeline runs synchronously in the Streamlit main thread. A 10–30 second Groq API call freezes the entire UI. There is no background task, no streaming, no progress updates mid-pipeline.

#### ❌ L10: Each Sandbox Run Creates + Deletes a `tempfile` Directory
**Where:** `execution/sandbox.py` → `sandbox_execute()`, called up to 7 times per run  
**Why it's a limitation:** Each of the 7 debug iterations creates `tempfile.mkdtemp()`, writes files, and then `shutil.rmtree()`s it. For fast iterations, the disk I/O becomes a measurable overhead on Windows (slow filesystem).

---

### 4.4 Practical / Deployment Limitations

#### ❌ L11: No Retry on API Rate Limit / Network Error
**Where:** `agents/translation_expert.py` → `generate_python()`, `agents/debug_expert.py` → `fix_code()`  
**Why it's a limitation:** If Groq's API returns a `RateLimitError` or `ConnectionError`, the exception propagates up to `run_pipeline()`'s bare `except Exception`, which catches it and marks the whole pipeline as `ERROR`. There is no retry with backoff.

#### ❌ L12: `requirements.txt` Is Critically Incomplete
**Where:** `requirements.txt`  
**Why it's a limitation:**
```
streamlit>=1.30.0
matplotlib>=3.8.0
numpy>=1.26.0
```
The file is missing: `openai`, `requests`, `python-dotenv`, `python-pptx` (used in scratch_run.py). A fresh `pip install -r requirements.txt` would leave the project broken at import time.

#### ❌ L13: Validation Tab in UI Shows Wrong / Stale Data
**Where:** `ui/app.py` lines 259–277  
**Why it's a limitation:** The validation tab reads `validation.get("is_valid")`, `validation.get("reason")`, `validation.get("confidence_score")`, and `validation.get("report")`. But `_step_validate()` in `main.py` returns keys `is_valid`, `pass_rate`, `stdout`, `stderr`, `returncode` — without `reason`, `confidence_score`, or `report`. The tab will always show empty/wrong data.

---

## 5. Solutions to Overcome Limitations

| # | Limitation | Concrete Fix |
|---|---|---|
| **L1** | RAG is a no-op | Use `sentence-transformers` + `chromadb` (or `FAISS`) to build a real vector store. Ingest COBOL-to-Python patterns, then do top-K semantic retrieval and inject into the translation prompt. |
| **L2** | Binary pass_rate | Capture `stdout` from sandbox, compare against `expected_output` from test cases. Use fuzzy match (`difflib`, `rapidfuzz`) for tolerance. |
| **L3** | Simulated baselines | Implement true systems: Baseline = call `generate_python()` with no context, no debug loop. RAG-Only = use context but skip `run_debug_loop()`. |
| **L4** | Dead `StructureExpert` | Either import and use it in `_step_build_analysis()`, or delete it to reduce confusion. |
| **L5** | Stale "DeepSeek" references | Run `grep -r "DeepSeek" .` and update all 5 occurrences in docstrings and log lines. |
| **L6** | Slider does nothing | Pass `max_retries` from sidebar to `run_pipeline()`: `run_pipeline(cobol_source, max_iter=max_retries)`. |
| **L7** | Empty KB | Add 20–30 COBOL-to-Python pattern documents to `data/knowledge_base/`. Start with your own test case translations. |
| **L8** | Narrow test suite | Add test cases for: file-reading programs, OCCURS tables, COMP-3 arithmetic, REDEFINES patterns, GO TO flows. Aim for 30–50 cases. |
| **L9** | Blocking pipeline | Use `st.spinner` + `concurrent.futures.ThreadPoolExecutor` to run the pipeline off the main thread. Consider streaming LLM responses. |
| **L10** | Repeated tempdir creation | Cache the tempdir across iterations within a single debug loop (create once, rewrite only the `.py` file per iteration). |
| **L11** | No API retry | Wrap Groq calls in `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential())`. |
| **L12** | Broken requirements.txt | Add: `openai>=1.0`, `requests>=2.28`, `python-dotenv>=1.0`, `tenacity>=8.0`, `sentence-transformers>=2.2` (for RAG). |
| **L13** | Wrong validation UI keys | Either update `_step_validate()` to return `reason` and `report` keys, or update the UI to read `pass_rate`, `stdout`, `stderr` from the existing dict. |

---

## 6. Future Work / Scope

### Research Directions
- **True Semantic Equivalence Testing:** Integrate a formal output extractor — run both the original COBOL (via GnuCOBOL) and translated Python, compare outputs line-by-line as ground truth.
- **CodeBLEU Scoring:** Calculate actual CodeBLEU scores against reference translations instead of relying only on execution success.
- **Mixture-of-Experts Router:** Replace the binary simple/complex router with a 5-class complexity taxonomy (arithmetic, conditional, loop, file-io, enterprise) and route to specialized sub-prompts.
- **Formal Verification Bridge:** After translation, generate Z3 solver constraints from both COBOL data declarations and Python variables to prove type-level equivalence.

### Advanced Features
- **Multi-File COBOL Support:** Handle `COPY` statements, `CALL` to subprograms, and multi-source file migrations with cross-reference resolution.
- **CICS/DB2 Stub Generation:** Detect CICS transaction codes and DB2 SQL inside COBOL, generate Python substitutes using Django ORM or SQLAlchemy.
- **Incremental Re-translation:** Hash each paragraph independently; re-translate only changed paragraphs when a COBOL file is updated.
- **Diff-Based Self-Debugging:** Instead of sending the entire broken file to the Debug Expert, send only the changed delta + error context to reduce token usage by 70%.

### Deployment & Scalability
- **FastAPI Backend:** Extract `run_pipeline()` into a FastAPI REST endpoint so any frontend (web, VS Code extension, CI/CD system) can call it.
- **Job Queue (Celery + Redis):** For enterprise use, queue migration jobs asynchronously, allowing dozens of files to be processed in parallel.
- **GitHub Action Integration:** Trigger pipeline on `.cob` file changes in a CI workflow, auto-generate PRs with translated Python.
- **VS Code Extension:** Embed the pipeline as a right-click "Translate to Python" command in a code editor plugin.

### Real-World Deployment
- **Cloud Deployment:** Package with Docker, deploy to Cloud Run (GCP) or AWS Lambda with API Gateway for on-demand usage.
- **Enterprise Mainframe Connector:** Build an SSH bridge that pulls COBOL source from mainframe JES2 job queues directly.

---

## 7. Final Evaluation

### Rating

| Dimension | Score | Comment |
|---|---|---|
| **Architecture Design** | 8/10 | Well-structured, clean separation of concerns |
| **Code Quality** | 7/10 | Readable, typed, well-commented; a few dead-code issues |
| **Error Handling** | 6/10 | Good at the sandbox layer; weak on API errors |
| **Prompt Engineering** | 9/10 | Exceptional — 23+ rules, checklists, edge cases covered |
| **Evaluation Framework** | 5/10 | Structure is good; data is partially simulated |
| **RAG Implementation** | 2/10 | Named RAG, doesn't function as RAG (empty KB, context not injected) |
| **UI / UX** | 7/10 | Clean Streamlit, but validation tab has broken data bindings |
| **Test Coverage** | 3/10 | 12 cases, no file-IO/OCCURS tests, no unit tests for modules |
| **Production-Readiness** | 4/10 | Missing retries, blocking pipeline, incomplete requirements |
| **Overall** | **6.5/10** | Strong foundation with clear, fixable gaps |

### Summary

This is a well-engineered research prototype that demonstrates genuine innovation in applying multi-agent LLM orchestration to legacy code migration. The **Translation Expert prompt** is a standout — it is one of the most detailed COBOL-to-Python rule sets likely written anywhere. The **sandbox design** is safe and creative (auto-stubbing IO files). The **debug loop** shows production-thinking with its stale-fix detector, dual timeouts, and rule-based fast-path.

However, three critical issues must be addressed before this can be called an "Agentic RAG" system:
1. **The RAG component must actually retrieve and inject context** — right now it is architecture-in-name-only.
2. **The evaluation baselines must be real, not probabilistically simulated** — the academic credibility of the paper depends on this.
3. **Validation must compare actual vs. expected output** — "code didn't crash" is not semantic correctness.

Fixing these three issues would elevate this from a solid prototype to a genuinely publishable system with defensible experimental results.
