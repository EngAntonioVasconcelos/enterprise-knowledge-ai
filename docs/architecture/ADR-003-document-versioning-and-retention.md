# ADR-003: Document Versioning and Retention

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision Owners:** Enterprise Knowledge AI Architecture

## 1. Context

Enterprise Knowledge AI ingests documents from multiple external
knowledge sources, initially Google Drive and Notion.

Documents may change over time, and the system must preserve
content consistency, support reliable retrieval, and maintain
appropriate access controls.

The platform must also handle synchronization and processing
failures without unnecessarily losing previously indexed content.

A document therefore needs a stable identity independent of its
content versions.

## 2. Decision

The system will adopt a Current Version + Selective History
versioning strategy.

The document lifecycle and version lifecycle will be managed
separately.

Each logical document will have:
- A stable identity.
- A reference to its current version.
- Source and organization metadata.
- A lifecycle state.
- Synchronization and processing information.

Each document version will represent an immutable snapshot
of a particular document state.

Historical versions will be retained selectively according
to organization-level retention policies.

## 3. Versioning Model

### 3.1 Document

The `Document` entity represents the logical identity of a
document, independently of its content versions.

It will reference its current version and maintain the metadata
required to identify its source and organization.

### 3.2 DocumentVersion

The `DocumentVersion` entity represents a specific snapshot
of a document's content.

Each version will:
- Belong to exactly one logical document.
- Have an internally managed version number.
- Store a SHA-256 content hash.
- Reference its stored content snapshot.
- Record creation and processing metadata.
- Maintain its version lifecycle information.

Version snapshots will be immutable after successful creation.
A new content state will result in a new version rather than
overwriting an existing snapshot.

### 3.3 DocumentChunk

Each `DocumentChunk` must belong to a specific
`DocumentVersion`.

Chunks from different versions must never be mixed in normal
document retrieval.

Normal retrieval will use chunks belonging to the current,
active, successfully indexed version only.

Historical retrieval, if enabled, will be a separate operation
subject to explicit authorization.

## 4. Change Detection

The system will use SHA-256 hashes to detect meaningful content
changes.

Before generating new chunks and embeddings, the ingestion
pipeline will compare the newly extracted content hash with
the existing version hash.

If the content has not changed, the system should avoid
creating a redundant version or repeating unnecessary
embedding operations.

Source-specific revision identifiers may also be stored when
available, but internal version numbering remains controlled
by Enterprise Knowledge AI.

### 4.1 Content Hashing Strategy

The SHA-256 hash will be calculated from normalized extracted
content rather than directly from the original binary file.

Normalization must be deterministic to ensure consistent
hash calculation across repeated ingestion operations.

Changes to embedding models, chunking strategies, or processing
pipeline configurations must be tracked independently from
document content versions.

A change in AI processing configuration may require
re-indexing without necessarily creating a new
DocumentVersion.

## 5. Version Activation and Processing Failures

A new version must not become the current version until its
content has been successfully processed and indexed.

The activation process must ensure that the database reference
to the current version and the corresponding retrieval state
remain consistent.

If extraction, chunking, embedding generation, or indexing
fails:
- The failure must be recorded.
- The system must support retrying the failed operation.
- The previous valid version must remain available, provided
  it is still authorized and active.
- An incomplete version must not be exposed through normal
  retrieval.

The activation of a new version must be performed through
a controlled and consistent database operation.

### 5.1 Index Activation Strategy

A new version must be fully processed and validated before
becoming available for normal retrieval.

The system will use a staged indexing approach.

Incomplete or failed indexing operations must not expose
partially processed document content.

When using PostgreSQL and pgvector within the same database,
the activation of the current version and the corresponding
retrieval visibility must be coordinated transactionally.

If an external indexing service is introduced in the future,
a dedicated consistency and publication strategy must be
defined.

## 6. Retention Policy

Retention will be configurable at the organization level.

The system will support:
- Selective preservation of historical versions.
- Retention periods defined by organizational policy.
- Administrative requests for permanent deletion.
- Auditable retention and deletion operations.

The platform must not assume that historical content can be
retained indefinitely.

Retention and deletion must respect applicable legal obligations,
source integration conditions, and organizational policies.

## 7. Removal and Access Revocation

Removing a document from an active knowledge source must
immediately prevent its content from appearing in normal
retrieval.

The system must distinguish between:
- Removing a document from active retrieval.
- Archiving historical content.
- Permanently deleting stored content.

Permission revocation must block access immediately, regardless
of whether historical versions remain stored.

Removal from retrieval must also account for derived data,
including chunks, embeddings, cached results, and other
retrieval references.

Permanent deletion must be coordinated across the storage
layer, database records, and derived data.

## 8. Security and Multi-Tenancy

Every document and its versions must remain associated with
the correct organization.

Authorization checks must be enforced before document content
is included in the context sent to an LLM.

The existence of a document in the retrieval index must never
be interpreted as authorization to access it.

Historical versions must follow the same organization isolation
and access control requirements as current versions.

## 9. Consequences

### Positive

- Preserves document history when needed.
- Prevents unnecessary embedding regeneration.
- Supports reliable document updates.
- Protects the last valid version during processing failures.
- Enables controlled historical retrieval.
- Improves traceability and auditability.

### Trade-offs

- Introduces additional data relationships.
- Requires version-aware ingestion and retrieval.
- Requires coordinated deletion of content and derived data.
- Adds complexity to retention and synchronization workflows.

## 10. Alternatives Considered

### Overwrite Existing Content

Rejected because it removes historical context and makes
document changes harder to audit.

### Preserve Every Version Indefinitely

Rejected as the default because it increases storage costs
and may conflict with retention and deletion requirements.

### Delete All Content Immediately on Source Removal

Rejected as the default because it does not support configurable
retention policies or controlled historical preservation.

## 11. Implementation Notes

This decision will guide the design of:
- `Document`
- `DocumentVersion`
- `DocumentChunk`
- `DocumentPermission`
- Document ingestion and synchronization services.
- Version-aware retrieval and deletion workflows.

Detailed database constraints, lifecycle states, retention
configuration, and storage implementation will be specified
before their respective implementation phases.
