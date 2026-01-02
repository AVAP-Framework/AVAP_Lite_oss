## Strategic Roadmap

Our vision is to build a high-performance, production-grade execution environment for the AVAP language. This project is structured into XI phases, moving from a foundational MVP to a global enterprise-scale architecture.

### Architecture at a Glance
* **Core:** Python (Tornado) for high-concurrency async I/O.
* **Execution:** Rust VM via PyO3 for memory safety and bare-metal performance.
* **Persistence:** PostgreSQL for source of truth and Redis for distributed caching.
* **Ops:** Kubernetes-native, Prometheus-monitored, and OpenTelemetry-traced.

### Current Status & Path to v1.0
We are currently executing the initial phases of our strategic plan:

1.  **Foundational (Phases I-III):** Establishing the Tornado/Rust bridge and secure sandboxing.
2.  **Production Ready (Phases IV-VI):** Implementing JIT compilation, layered caching, and observability.
3.  **Enterprise Scale (Phases VII-XI):** Hardening, multi-region deployment, and automated scaling.

> [!TIP]
> **For the full technical specification, including detailed components, performance targets, and risk mitigation, please see our [Detailed Strategic Roadmap (ROADMAP.md)](./ROADMAP.md).**

![CI](https://github.com/AVAP-Framework/AVAP_Lite_oss/actions/workflows/ci.yml/badge.svg)