# ADR-004: Document Storage Strategy

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision Owners:** Enterprise Knowledge AI Architecture

## 1. Context

Enterprise Knowledge AI must ingest, process, and retain documents
from external knowledge sources, initially Google Drive and Notion.

The platform needs to store original files, immutable document
version snapshots, structured metadata, extracted content,
document chunks, and vector embeddings.

The storage architecture must support:
- Multi-tenant data isolation.
- Document versioning and selective retention.
- Efficient semantic retrieval.
- Reliable document ingestion.
- Local development and public deployment.
- Future storage provider changes without rewriting
  business logic.

## 2. Decision

The system will adopt a hybrid storage architecture combining
PostgreSQL with an S3-compatible object storage service.

Storage responsibilities will be separated into three areas:

1. Relational metadata and application data.
2. Document files and version snapshots.
3. Search chunks and vector embeddings.

The application will interact with object storage through
a storage abstraction layer.

## 3. PostgreSQL

PostgreSQL will store structured application data, including:
- Organizations and users.
- Documents and document versions.
- Document permissions.
- Integration and synchronization metadata.
- Processing and indexing states.
- Object storage references.
- Document chunks and associated metadata.

PostgreSQL with pgvector will initially provide vector
storage and similarity search.

Document metadata and relationships must preserve
organization-level isolation.

## 4. Object Storage

Original document files and immutable version snapshots
will be stored in an S3-compatible object storage service.

The database will store references to these objects
rather than their binary contents.

Each stored object must have:
- A unique object key.
- An associated organization.
- An associated document and, where applicable, version.
- A content type.
- A content size.
- A cryptographic checksum where appropriate.
- Creation and storage metadata.

Object keys must not be treated as authorization mechanisms.
Access must be controlled by the application and storage layer.

### 4.1 Original Files and Normalized Content Snapshots

The storage architecture must distinguish between original
source files and normalized content snapshots.

Original files must be preserved when available and permitted
by the source integration and retention policies.

Normalized content snapshots represent the extracted and
deterministically normalized content used by the ingestion
and retrieval pipeline.

Both original files and normalized snapshots will be stored
in object storage.

DocumentVersion metadata in PostgreSQL will maintain
references to the corresponding stored objects.

This separation allows the platform to reprocess documents
without requiring repeated downloads from external sources.

## 5. Storage Abstraction

The application will define a storage interface independent
of the underlying storage provider.

The initial implementations will be:

### 5.1 LocalStorageBackend

Used for local development and testing.

It will store objects in a controlled local directory.

### 5.2 S3StorageBackend

Used for deployment environments through an S3-compatible
object storage provider.

The application must not depend directly on provider-specific
operations in its business logic.

Changing storage providers should require configuration
changes or a storage adapter implementation rather than
changes to document processing and business services.

## 6. Document Storage Lifecycle

The storage lifecycle will support:
- Uploading or importing original documents.
- Storing immutable version snapshots.
- Retrieving stored objects through authorized operations.
- Retaining historical snapshots according to retention policies.
- Deleting objects when permanent deletion is authorized.

Object storage operations and PostgreSQL transactions
cannot be assumed to be atomic.

The ingestion workflow must therefore handle partial failures,
orphaned objects, retry operations, and cleanup procedures.

The system must not publish a document version as current
until its required content and indexing operations have
successfully completed.

### 6.1 Cross-Storage Consistency

PostgreSQL transactions and object storage operations
must be treated as independent operations.

The application must support:
- Idempotent storage operations where possible.
- Tracking the state of storage-related operations.
- Retrying incomplete operations.
- Detecting and cleaning orphaned objects.
- Preventing deletion of objects that still have valid references.

Cleanup operations must verify database references before
permanently deleting stored objects.

The system must favor recoverable operations over
irreversible actions when consistency cannot be confirmed.

## 7. Security

The storage architecture must support:
- Organization-level isolation.
- Encryption in transit.
- Encryption at rest where supported.
- Restricted storage credentials.
- Private object storage by default.
- Authorized access through application-controlled operations.
- Secure handling of temporary download links, if introduced.

Storage object keys must never expose sensitive document
contents or personal information.

## 8. Retention and Deletion

Object storage retention must follow the document versioning
and retention strategy defined in ADR-003.

Permanent deletion must account for:
- Original files.
- Historical version snapshots.
- Associated database metadata.
- Document chunks and embeddings.
- Cached or derived content where applicable.

Deletion operations must be auditable and resilient to
partial failures.

## 9. Consequences

### Positive

- Separates structured data from binary document storage.
- Supports scalable document storage.
- Enables provider-independent application logic.
- Supports local development and cloud deployment.
- Aligns with selective document version retention.
- Keeps PostgreSQL focused on relational data and retrieval.

### Trade-offs

- Requires an additional storage component.
- Requires handling failures across independent storage systems.
- Requires cleanup and consistency mechanisms.
- Introduces storage configuration and operational costs.

## 10. Alternatives Considered

### Store Binary Documents Directly in PostgreSQL

Rejected as the default because it mixes large binary objects
with application metadata and increases database storage
and operational overhead.

### Use Local Filesystem as the Production Storage Layer

Rejected because local filesystem storage does not provide
the portability and operational characteristics required
for the intended deployment architecture.

### Couple Business Logic Directly to a Cloud Provider

Rejected because it creates unnecessary vendor dependency
and makes storage provider changes more expensive.

## 11. Implementation Notes

This decision will guide the design of:
- The storage abstraction interface.
- Local and S3-compatible storage adapters.
- Document and version storage references.
- Document ingestion and deletion workflows.
- Storage configuration and security controls.
- Object lifecycle and cleanup operations.

The specific object storage provider, bucket configuration,
encryption settings, and deployment infrastructure will be
selected during the implementation and deployment phases.
