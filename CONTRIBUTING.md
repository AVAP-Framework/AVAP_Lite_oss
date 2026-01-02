# Contributing to AVAP Lite

Thank you for your interest in contributing to AVAP Lite! This project is a specialized bridge between the agility of Python (Tornado) and the high-performance safety of Rust. 

---

## 🛠️ Technical Environment Setup

Developing for this project requires configuring both Python and Rust ecosystems.

### Prerequisites
* **Python 3.11+**
* **Rust & Cargo** (Latest stable version)
* **Maturin**: Required tool to build and publish Rust-Python bindings.
* **Docker & Docker Compose**: To run local PostgreSQL and Redis instances.

### Local Development Workflow
1. **Clone and Setup Python**:
   ```bash
   git clone [https://github.com/AVAP-Framework/AVAP_Lite_oss.git](https://github.com/AVAP-Framework/AVAP_Lite_oss.git)
   cd AVAP_Lite_oss
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt



2. **Compile the Rust VM**:
For Python to interact with the Rust core, you must compile the library locally:
```bash
maturin develop

```


3. **Running Tests**:
* Python tests: `pytest`
* Rust core tests: `cargo test`



---

## Development Standards

### Execution Pipeline Integrity

The execution flow is: **Source → Parser → Intermediate Representation (IR) → Rust VM**.

If you modify the Parser or the Bytecode format:

1. Ensure backward compatibility with existing AVAP scripts.
2. Update the instruction set documentation in `docs/architecture.md`.
3. Add a regression test for sandbox boundary verification.

### Quality Attributes (Success Criteria)

All contributions must align with our core principles:

* **Security**: No execution of arbitrary Python code; strict resource limits.
* **Performance**: Minimal overhead per command execution.
* **Reliability**: Graceful error handling and resource leak prevention.

---

## Communication Channels & Governance

The project utilizes a dual communication structure to balance agility with rigorous technical documentation.

### Communication Matrix

| Platform | Primary Function | Content Type |
| --- | --- | --- |
| **Slack** | **Synchronous Coordination** | Active discussion, brainstorming, status updates. |
| **GitHub** | **Asynchronous Record** | Technical specs, bug reports, RFCs, permanent docs. |

### "Source of Truth" Policy

1. **Slack is not documentation.** Agreements made in chat must be transferred to an *Issue* or *Pull Request* to be considered official.
2. **Transparency.** We strongly encourage the use of public channels over DMs to foster knowledge transfer.

---

## Pull Request Process

1. Create a descriptive feature branch.
2. Ensure all tests pass (`pytest` and `cargo test`).
3. If your change completes a part of the strategic plan, update **ROADMAP.md**.
4. Open the PR and wait for review.

By contributing, you agree that your contributions will be licensed under the project's Open Source license.




