# Project Draft: COBOL to Python Migration Pipeline

## Abstract

Legacy system modernization remains a critical challenge for enterprises relying on decades-old COBOL codebases, which are increasingly costly to maintain due to a shrinking pool of specialized developers. To address this, we present an end-to-end, AI-powered multi-agent pipeline designed to automate the translation of legacy COBOL programs into idiomatic Python. Our approach introduces a dynamic multi-agent architecture comprising specialized expert agents—including Router, Structure, Translation, Test, and Debug agents—augmented by a Retrieval-Augmented Generation (RAG) knowledge engine to provide context-aware translation. Furthermore, the system incorporates a self-debugging execution loop that actively sandboxes, runs, and refines the generated code to ensure operational correctness. To validate the efficacy of our system, we developed a research-grade evaluation framework that rigorously compares baseline Large Language Models (LLMs) against our RAG-only and full agentic-RAG architectures. Our evaluation highlights that coupling multi-agent orchestration with iterative self-debugging and context retrieval significantly reduces unhandled errors, minimizes silent failures, and yields high-confidence Python conversions, thereby offering a highly scalable and robust solution for legacy software modernization.

**Index Terms:** Legacy System Modernization, COBOL to Python Migration, Multi-Agent Architecture, Retrieval-Augmented Generation (RAG), Large Language Models (LLMs), Self-Debugging Execution, Automated Transpilation

## Introduction

The foundational infrastructure of many critical financial, governmental, and enterprise systems relies heavily on COBOL (Common Business-Oriented Language). Despite its historical reliability, maintaining these legacy systems is fraught with growing challenges, including rigid architectures, mounting technical debt, and a rapidly declining workforce equipped with necessary legacy domain expertise. Consequently, modernizing these monolithic applications by migrating them into versatile, widely-supported, and agile languages like Python has become a strategic imperative. However, manual conversion is notoriously slow, expensive, and error-prone, while traditional rule-based automated transpilers often produce cumbersome and unidiomatic code that is difficult for modern developers to maintain.

Recently, Large Language Models (LLMs) have demonstrated immense promise in natural language understanding, automatic code generation, and translation. Yet, deploying LLMs continuously out-of-the-box for complex COBOL-to-Python migrations frequently results in flawed code. These failures stem from the stark paradigm differences between the two languages—such as COBOL's strict division structures, data declaration styles, and procedural logic versus Python's dynamic typing and object-oriented nature. 

To bridge this translation gap and ensure reliable outputs, we introduce a sophisticated Agentic RAG (Retrieval-Augmented Generation) code migration pipeline. Rather than relying on a single-pass LLM prompt, our system employs a multi-agent orchestrated workflow. It decomposes the complex task of code migration and assigns specialized intelligent roles: a **Router Agent** to evaluate task complexity, a **Structure Expert** to accurately parse structural divisions and memory variables, a **Translation Expert** for idiomatic syntax conversion, a **Test Expert** to generate validation cases, and a **Debug Expert** to handle errors. 

Crucially, this agentic pipeline integrates two key components to guarantee high fidelity:
1. **Retrieval-Augmented Generation (RAG):** Contextual domain knowledge is fetched directly from an ingested code repository to inform the translation model with program-specific specifics.
2. **Execution Context and Self-Debugging:** The system utilizes a sandboxed execution environment to iteratively run, validate, and debug generated translations—simulating a human developer's trial-and-error approach.

In this project, we detail the implementation of this comprehensive pipeline and present a robust evaluation framework that quantitatively measures its performance. Through comparative analyses against raw LLMs and RAG-only strategies, this research aims to demonstrate that context-aware retrieval paired with multi-agent self-correction provides an unparalleled jump in the confidence, correctness, and speed of automated code modernization.

## II. Problem Statement

The modernization of legacy systems, particularly those written in COBOL, is a pressing necessity due to high maintenance costs, a shrinking talent pool, and difficulty integrating with contemporary cloud and web technologies. While transitioning to a modern, versatile language like Python is the logical solution, the process is fraught with risks. Manual translation is prohibitively slow, expensive, and error-prone, whereas traditional rule-based transpilers often yield unidiomatic, rigid code that is equally difficult to maintain. Recent advancements in Large Language Models (LLMs) offer a promising automated alternative; however, using LLMs out-of-the-box for continuous translation typically leads to hallucinated, structurally flawed, and incorrect code. This is because standard models fail to grasp the stringent architectural paradigms of COBOL (e.g., specific memory layouts and procedural rigidity) and lack the contextual knowledge of the wider application environment. Therefore, a critical need exists for an intelligent, automated framework that can not only generate idiomatic Python from complex COBOL structures but also iteratively verify, debug, and refine the translated code using an environment-inclusive feedback loop. 

## III. Related Work

The landscape of automated code generation and system migration has evolved significantly, particularly with the advent of advanced Large Language Models and multi-agent systems.

**Multi-Agent Code Generation and Collaboration**
LLMs have fundamentally shifted the paradigm in automatic programming. Recent studies demonstrate that multi-agent collaborative frameworks drastically outperform single-agent prompting. For example, Zhang et al. introduced *PairCoder*, an LLM-based framework that mimics pair programming through a Navigator agent for high-level planning and a Driver agent for implementation. This approach's multi-plan exploration and feedback-driven refinement resonate with our architecture, highlighting the efficacy of dividing labor among specialized AI personas to tackle intricate implementation challenges.

**Code Migration and Environment Interaction**
Translating code across different languages and ecosystems requires more than syntactic mapping. Li et al. in *Environment-in-the-Loop* argue that automated code migration is incomplete without simultaneous environment interaction and compilation checks. Their emphasis on feedback cycles directly informs our self-debugging loop. Furthermore, the *FreshBrew* benchmark by May et al., designed to evaluate AI agents on Java code migration, illustrates that while powerful LLMs demonstrate remarkable capability in modernizing codebases, they still struggle with semantic preservation in realistic project-level environments, underscoring the absolute necessity of rigorous validation through testing.

**RAG and Expert Architecture in Reasoning**
The need for high-fidelity code conversion necessitates reducing hallucination. Retrieval-Augmented Generation (RAG) effectively supplies models with specific, up-to-date context. Work on *OPEN-RAG* by Islam et al. illustrates that transforming standard LLMs into sparse Mixture-of-Experts (MoE) architectures considerably enhances parameter efficiency and reasoning over complex, multi-hop queries. Concurrently, Gumaan's theoretical framework, *ExpertRAG*, integrates MoE with dynamic retrieval to selectively balance parametric knowledge with factual recall. These advancements confirm that grounding an agentic pipeline with dynamically accessed domain knowledge is paramount for scaling language modeling effectively.

**Iterative Refinement and Verification**
Static code generation often misses obscure edge cases or underlying systemic constraints. Research exploring the integration of formal verification and LLMs, such as the neuro-symbolic loop invariant inferences by Wu et al., demonstrates the value of iterative querying paired with Bounded Model Checking (BMC). Their "query-filter-reassemble" strategy effectively leverages external solvers to filter hallucinated LLM responses, confirming that an iterative execution-verification-debugging cycle is the most viable path toward guaranteed target-code correctness. 

**Efficiency of Small Language Models**
While monumental LLMs push boundaries, smaller models remain crucial for scalable deployment. An empirical study by Hasan et al. on Small Language Models (SLMs) for code generation demonstrates that compact models (under 10B parameters) can achieve competitive functional correctness for multiple programming languages. However, their findings also highlight a stark trade-off between strict functional bounds and required VRAM consumption. Employing an orchestrated multi-agent RAG pipeline helps offset these limitations by compartmentalizing context.

## IV. Methodology

To overcome the limitations of isolated LLM prompts in complex code translation, we engineered an end-to-end, multi-agent AI pipeline. The architecture is strategically designed to parse legacy COBOL accurately, translate it into idiomatic Python, and iteratively enforce correctness through an automated debugging sandbox.

The proposed methodology consists of five primary stages:

**1. Preprocessing and Chunking**
Because COBOL programs are often monolithic and densely structured into strict divisions, raw code ingestion leads to context window explosion and hallucination. The preprocessing phase systematically normalizes the target COBOL source code and chunks it logically by procedure, paragraph, and division to ensure fine-grained handling.

**2. Context Integration via Retrieval-Augmented Generation (RAG)**
To ground the translation in program-specific logic and domain nuances, we utilize a RAG engine. Before translation, knowledge vectors containing structural mappings, internal dependencies, and project-specific definitions are retrieved from an external knowledge base. This guarantees that the models have immediate access to relevant variables and macro definitions natively found within interconnected legacy files.

**3. Multi-Agent Orchestration Pipeline**
The core translation logic is driven by a cooperative multi-agent system. Tasks are divided among distinct expert agents to minimize overlapping responsibilities and maximize translation fidelity:
*   **Router Agent:** Initially classifies the incoming code chunk's complexity (e.g., simple vs. complex) to determine the optimal agent processing flow.
*   **Structure Expert:** Parses intrinsic COBOL elements, specifically managing divisions, control blocks, and variable memory maps to preserve the original logic flow.
*   **Translation Expert:** Analyzes the output from the Structure Expert alongside RAG context to convert the COBOL constructs into syntactically valid and idiomatic Python code.
*   **Test Expert:** Simultaneously generates exhaustive test cases (including happy path, boundary, and error handling) based on the intended functionality to validate the generated Python code.

**4. Execution Sandbox and Self-Debugging Loop**
A pivotal component of our methodology is the environment-in-the-loop interaction. Once the corresponding Python translation and test scripts are generated, they are deployed in an isolated Python subprocess executor (a "sandbox"). If the generated code triggers execution failures or fails the generated tests, the resulting stack traces and error logs are captured and fed directly back into our **Debug Expert**. The Debug Expert subsequently analyzes the errors and regenerates patched code. This iterative self-debugging cycle continues until all tests pass or a predefined retry threshold is reached.

**5. Validation and Evaluation**
Finally, a validator evaluates the resultant Python code. It assigns a confidence score evaluating the correctness, structural proximity, and testing success rate. To scientifically gauge the holistic system performance, we employ a comparative research-grade evaluation framework. The final configurations are stress-tested against:
*   A naive **Baseline LLM** (single-pass translation).
*   A **RAG-Only** configuration without a robust debug loop.
*   The **Full Agentic RAG** configuration to measure the absolute compounding benefit of sequential expert processing and automated debugging.
