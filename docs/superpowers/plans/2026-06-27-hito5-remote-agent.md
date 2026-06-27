# Hito 5 — Remote Secure Agent — Plan

> The highest-risk component (docs 05). Decomposed into shippable, mostly-testable
> slices. The *local* agent already validates the `run_on: agent` routing contract
> (ADR-0017); Hito 5 adds the secure remote operation around it.

## Constraints in this environment
- The Temporal **dev server** doesn't do mTLS easily → slice 4 (mTLS↔Temporal) is
  only partially verifiable here; we implement the wiring + denylist and unit-test
  the crypto, deferring a real-mTLS smoke to a TLS-enabled Temporal.
- CA, cert issuance, and per-agent envelope encryption are pure crypto → fully
  testable offline with `cryptography`.

## Slices (each ends green: tests + lint + types)

### Slice 1 — Agent registry & lifecycle  ← FIRST
The "Agent Manager": enroll → register → approve → revoke, with a state machine.
- Single-use, short-lived **enrollment token** behind an injectable `AgentTokenStore`
  (Redis impl `SET NX EX` + `GETDEL`; fake in tests).
- `agents` service: `register_agent` (creates `pending_approval`, stores `public_key`,
  `task_queue=agent-<id>`), `approve_agent`, `revoke_agent`, `list/get`.
- Endpoints: `POST /agents/enroll` (admin → token + temporal endpoint),
  `POST /agents/register` (agent: token + name + public_key → agent),
  `GET /agents`, `POST /agents/{id}/approve` (admin), `POST /agents/{id}/revoke` (admin).
- State machine: register→pending_approval→approved→(online↔offline)→revoked. Audit all.

### Slice 2 — Internal CA + certificate issuance
- A self-signed **CA** (config/seeded). `sign_csr(csr) -> cert` + fingerprint.
- Registration signs the agent's CSR, persists `fingerprint`, returns the cert.
- Pure `cryptography`; unit-tested (issue cert, verify chain + fingerprint).

### Slice 3 — Per-agent envelope encryption (ADR-0013)
- Agent keypair at enroll (agent generates; sends public key). `agents.public_key` stored.
- When a `run_on: agent` job carries `secret://`, the server encrypts each secret to
  the **agent's public key** (envelope: random data key + RSA/X25519 wrap). The agent
  decrypts in memory only. The agent never holds the master key (replaces the shared
  codec key for agent payloads). Unit-tested (encrypt→decrypt roundtrip; wrong key fails).

### Slice 4 — mTLS agent↔Temporal + revocation enforcement
- Agent connects to Temporal with its cert; **fingerprint** verified; revoked agents
  denied (CRL/denylist). Implement wiring + denylist; unit-test the denylist/fingerprint
  checks; real-mTLS smoke deferred to a TLS Temporal.

### Slice 5 — Agent UI
- Admin **Agents** page: list + status, enroll (show token), approve, revoke.

## Order rationale
1 establishes the registry everything hangs off; 2–3 add the crypto guarantees;
4 is the infra-gated piece; 5 makes it operable. Stop-and-review between slices.
