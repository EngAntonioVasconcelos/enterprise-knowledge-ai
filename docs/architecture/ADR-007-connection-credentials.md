# ADR-007: Connection credentials

- Status: accepted
- Date: 2026-11-14

## Context

A connection's credentials (an OAuth refresh token, a read-only database
user and password) open the customer's systems. They are the most
sensitive data the platform holds. ADR-006 requires them to be encrypted
with a per-organization key, never returned by the API, never logged.

The API receives credentials from an admin. The worker uses them to
synchronize. The API is also the component most exposed to attack.

## Decision

Asymmetric envelope encryption, so that the API can store a secret but
nothing it holds can open one.

- **Master key pair** (platform): X25519. The API is configured with the
  public half only (`CREDENTIALS_MASTER_PUBLIC_KEY`); the worker with the
  private half (`CREDENTIALS_MASTER_PRIVATE_KEY`). In development both sit
  in `backend/.env`, created by `python -m scripts.generate_master_key`; in
  production the private half lives in a KMS (Phase 10).
- **Organization key pair**: created by the API on first use. Its private
  half is sealed to the master public key at once and only stored sealed.
- **Credential**: JSON, sealed to the organization's public key.
- **Sealing**: ephemeral X25519, HKDF-SHA256, AES-256-GCM (library:
  `cryptography`). The associated data binds a value to its place:
  `eka:organization-key:v1:<org>` and `eka:credential:v1:<org>:<connection>`.
  A sealed value copied to another organization or connection does not open.
- **Database**: `organization_keys` and `connection_credentials`, forced
  row-level security. `eka_runtime` may insert and replace, and may read
  only metadata columns (existence, fingerprint, dates), never the sealed
  bytes. `eka_worker` reads them only for the organization of its current
  job. Nobody deletes directly.
- **Disconnecting** a source destroys its secret (trigger). Setting,
  replacing and destroying are audited with the key fingerprint, never the
  content.
- **Testing a connection** is a worker job, so the API never needs a secret
  in clear after receiving it.

## Consequences

- Compromising the API (code or its database role) does not reveal stored
  credentials. Compromising a database copy does not either: the master
  private key is not in the database.
- Destroying an organization's key makes all its secrets unreadable,
  backups included (crypto-shredding), which serves GDPR deletion. The
  procedure is part of the Phase 10 deletion work.
- Every organization key records the master key fingerprint that sealed
  it, so the master key can be rotated by re-sealing organization keys
  without touching any credential.
- Losing the master private key loses every credential: in production it
  stays in a KMS with its own backups. `generate_master_key` refuses to
  overwrite an existing key for that reason.

## Alternatives considered

- **Symmetric master key in the API.** Simpler, but whoever controls the
  API can decrypt everything. Rejected.
- **Database encryption only (pgcrypto, disk encryption).** Protects disks,
  not a compromised application or role. Rejected as the only layer.
- **External secret manager per credential.** Good for production at
  scale; the interface here keeps that option open for Phase 10.
