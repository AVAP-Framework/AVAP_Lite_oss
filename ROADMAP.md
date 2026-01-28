# AVAP Language Server: Strategic Roadmap

This document defines the technical evolution of the AVAP Language Server, merging core VM architecture with enterprise-grade cloud infrastructure.

---

## Project Vision
To build a production-grade execution engine for the AVAP scripting language that ensures:
* **Performance**: Bare-metal execution speed via a Rust VM.
* **Security**: Strict sandboxing with resource quotas (CPU, Memory, Time).
* **Scalability**: Horizontal growth from a single node to an auto-scaled Kubernetes cluster.

---

## Core Architecture & Pipeline
The server transforms raw script into results through a high-performance pipeline:
`AVAP Source` ➔ `Parser` ➔ `JSON AST` ➔ `Command Resolution` ➔ `Bytecode JIT` ➔ `Rust VM Execution` ➔ `Result Collection`

---

## Development Journey

### Phase I: Foundation (The MVP)
- [x] ~~**Server Core**: Tornado async HTTP server with health endpoints.~~
- [x] ~~**Persistence**: PostgreSQL integration (`obex_dapl_functions`) and connection pooling.~~
- [x] ~~**Base Parser**: Syntax validation and command recognition.~~
- [x] ~~**Lifecycle**: Orderly initialization and graceful shutdown logic.~~

### Phase II: Bytecode & JIT Compilation
- [x] ~~**Bytecode Spec**: Custom binary format with version headers and digital signatures.~~
- [x] ~~**Compiler**: Python AST transformation into intermediate representation (IR).~~
- [x] ~~**Bytecode Storage**: Implementation of the `avap_bytecode` table with hash-based versioning.~~
- [x] ~~**Optimization**: Initial pipeline for bytecode performance tuning.~~

### Phase III: Advanced Rust VM & Sandboxing
- [x] ~~**VM Core**: Complete instruction set (Scopes: Global, Local, Function).~~
- [ ] **Memory Isolation**: Dedicated stack management per execution context.
- [ ] **Security Sandbox**: 
    - [ ] CPU instruction/cycle quotas.
    - [ ] Execution wall-clock timeouts.
    - [ ] Memory allocation limits.
- [ ] **Thread Management**: Offloading VM tasks to Rust threads to bypass Python's GIL.

### Phase IV: Performance & Caching
- [x] **Layered Caching**: 
    - L1: Memory (LRU) 
    - L2: Redis (Distributed) 
    - ~~L3: PostgreSQL (Persistent).~~
- [x] ~~**Async Request Handling**: Rate limiting (IP/API Key) and request queuing for overload protection.~~
- [x] ~~**Performance Benchmarking**~~:
    - ~~[x] Baseline established on Apple M2 (6.8k RPS).~~
    - ~~[x] Stress testing on 2-vCPU constrained nodes (5.1k RPS).~~
    - ~~[x] Tier 1 Certification achieved.~~
- [ ] **Response Optimization**: Response compression (gzip) and keep-alive management.
### Phase V: Persistence & Distributed Systems
- [ ] **Distributed Cache**: Pub/Sub for inter-node cache invalidation.
- [ ] **Session Storage**: Handling persistence for long-running script executions.
- [ ] **Local Fallback**: Embedded storage for offline mode and core commands.

### Phase VI: Observability & Telemetry
- [ ] **Structured Logging**: JSON logs with correlation IDs for ELK/Loki.
- [ ] **Metrics**: Prometheus exporters (Success rates, VM latency, Resource usage).
- [ ] **Distributed Tracing**: OpenTelemetry spans for end-to-end request tracking.
- [ ] **Debug Endpoints**: Internal diagnostics and production performance profiling.

### Phase VII: Security & Hardening
- [ ] **API Hardening**: Request signing, HSTS, and CSP headers.
- [ ] **Server Hardening**: Non-root container execution and network interface binding.
- [x] ~~**Audit & Compliance**: Full audit trail of script executions and admin operations.~~
- [ ] **DDoS Protection**: Basic mitigation and request sanitization.

### Phase VIII: Scalability & High Availability (HA)
- [ ] **Multi-node Ops**: Service discovery and load balancing between instances.
- [ ] **Distributed Job Queue**: Async job prioritization and exponential backoff retries.
- [x] ~~**Resiliency**: Circuit breakers and Bulkhead isolation for fault tolerance.~~
- [x] ~~**Chaos Engineering**: Readiness~~ testing for infrastructure failure.

### Phase IX: Deployment & CI/CD (K8s)
- [ ] **Containerization**: Optimized multi-stage Docker builds with security context.
- [ ] **Orchestration**: Kubernetes manifests (Deployments, HPA, Network Policies).
- [ ] **Automated Pipeline**: 
    - [ ] Security scanning of images.
    - [ ] Automated performance benchmarking.
    - [ ] Canary and Blue/Green deployment automation.

---

## Performance Targets

| Milestone | Requests/sec (per node) | P95 Latency | Status |
| :--- | :--- | :--- | :--- |
| **Phase I-III (MVP)** | 100 | < 100ms | 🟢 Met |
| **Phase IV-VI (PROD)** | 5,000+ | < 210ms* | 🟢 Exceeded |
| **Phase VII-IX (SCALE)** | 10,000+ | < 15ms | 🟡 In Progress |

*\*P95 latency of 210ms is a constant safety boundary established during Tier 1 Certification.*
> [!NOTE]
> **Performance Validation**: Detailed technical evidence of these milestones is documented in our [Performance Audit (PERFORMANCE.md)](./PERFORMANCE.md).

---

## Technical Specifications
* **Frontend**: Python 3.11+ (Tornado, PyO3).
* **Core**: Rust (VM, Bytecode Parser).
* **Persistence**: PostgreSQL (`asyncpg`), Redis.
* **Infra**: Docker, Kubernetes, Prometheus, OpenTelemetry.

---

## Risks & Mitigations
* **VM Stability**: Exhaustive unit testing and memory safety via Rust.
* **Database Load**: Aggressive bytecode caching and connection pooling.
* **Scaling Bottlenecks**: Multi-node architecture with distributed locking and state management.