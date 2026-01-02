# AVAP Language Server Lite Architecture

This document describes the internal workings of the AVAP execution engine.

## Execution Pipeline
1. **Request Layer (Python/Tornado)**: Receives the AVAP script via REST API.
2. **Parsing Layer (Python)**: Validates syntax and generates a **JSON-based AST**.
3. **Compilation Layer (Python/JIT)**: Transforms the AST into an **Intermediate Representation (IR)** / Bytecode.
4. **Execution Layer (Rust VM)**: The IR is passed to the Rust core via **PyO3**. The VM executes the instructions in a thread-safe, sandboxed environment.
5. **Context & Scopes**: The VM manages three distinct variable pools (Global, Local, and Function-scoped) to ensure script integrity.

## Key Technologies
* **Tornado**: Non-blocking web server for handling high-concurrency requests.
* **Rust**: Used for the Virtual Machine to guarantee memory safety and execution speed.
* **PyO3**: The bridge that allows seamless data transfer between Python and Rust.
* **PostgreSQL**: Stores the command registry and compiled bytecode for rapid retrieval.