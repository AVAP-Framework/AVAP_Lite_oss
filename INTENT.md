# AVAP: Architecture Intent & Logic Flow (Draft)

This document serves as the conceptual blueprint for the AVAP ecosystem, moving away from fixed binary specifications toward a **Contract-Based Execution Model**.

---

## 1. The Core Philosophy: Subordinated Logic
AVAP is built on the principle that the **Execution Node (Worker)** should be "blind" and "stateless" until a **Central Authority (Brain)** provides signed, verified instructions.

* **Integrity over Auth**: Traditional APIs rely on *who* is calling. AVAP relies on *what* is being executed.
* **Late-Binding Contracts**: Logic is not hardcoded into the Worker; it is injected and verified at runtime through a cryptographic handshake.



---

## 2. The Logic Flow (The Handshake)

1.  **Synchronization Phase**: At startup, the Worker initiates a gRPC `SyncCatalog` call to the Brain.
2.  **Definition Ingestion**: The Brain provides a signed catalog of command interfaces and their corresponding logic.
3.  **L1 Residency**: The Worker stores these definitions in a zero-latency RAM cache.
4.  **Request Validation**: When an execution request arrives, the Worker validates the integrity of the command using the cached signature.
5.  **Sandboxed Execution**: The logic is executed within a restricted environment (currently Python, moving to Rust VM).



---

## 3. The Evolution Toward Contract-Based Security
The current version uses **HMAC-SHA256** for simple integrity. The project is moving toward **Execution Contracts**, which will define:

* **Resource Quotas**: Hard limits on memory, CPU cycles, and wall-clock time per execution.
* **Capability Scopes**: Granular permissions defining which external connectors (DB, HTTP, etc.) the specific command is allowed to touch.
* **Ephemeral Identity**: The ability to sign logic with short-lived certificates, allowing for "Time Travel" and instant revocations.



---

## 4. Current Implementation State (v0.x)
* **Brain**: Node.js-based Definition Server.
* **Worker**: Python/Tornado orchestrator with a Rust-based VM core (via PyO3).
* **Integrity**: Static HMAC signatures derived from a shared internal key.

---

## 5. Vision for v1.0 (The Independent Standard)
The goal is for AVAP to become a **Language-Agnostic Standard**.
* **Interoperable Brains**: Any Definition Server should be able to issue compliant contracts.
* **Polyglot Workers**: Any Worker (in Rust, Go, Zig, etc.) should be able to enforce those contracts.
* **SPOF Elimination**: The "Single Point of Failure" of the original creator is eliminated by standardizing this communication protocol.

---
© 2026 AVAP Sphere.