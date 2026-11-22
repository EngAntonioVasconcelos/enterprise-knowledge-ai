# File uploads

Members upload PDF, Word (.docx) and text files into a `file_upload`
connection. Uploads are a source like any other: the `file_upload`
connector feeds them to the sync engine, so versions, permissions and
removal work exactly as for Google Drive. Migration `d4a1e7b3c8f2`.

## Flow

1. `POST /organizations/{org}/connections/{id}/uploads/` (multipart:
   `file`, `visibility` = `organization` or `private`). Owners, admins and
   members; viewers read only.
2. The API checks the size (20 MB), the real type from the bytes (not the
   name), stores the original under `org/connection/uploads/<id>/original`
   and queues the connection's sync. It does not parse the file.
3. The worker's sync lists every active upload (complete listing) with
   the upload's SHA-256 as revision: an unchanged file is not read again.
   New files are parsed (`app/services/text_extraction.py`), versioned and
   given their permission: the whole organization, or the uploader alone.
4. `DELETE .../uploads/{id}` (uploader only): the next sync takes the
   document out of retrieval; versions stay for retention.

## Privacy and safety

- Upload records (file names) are visible to the uploader only, owners
  included; documents follow their visibility.
- The database refuses an upload that is not by the caller, under the
  caller's own e-mail, into a live `file_upload` connection of an
  organization the caller belongs to.
- Members may see upload connections of their organization and queue
  their sync; nothing else about connections or jobs.
- Parsing has limits: 20 MB per file, 100 MB unzipped for Word files
  ("zip bombs"), 2000 PDF pages, password-protected PDFs refused. A file
  without text (a scanned PDF) fails with a clear message and does not
  stop the other files; text recognition (OCR) comes later.

## Dependencies

`python-multipart` (form uploads), `pypdf` (PDF), `python-docx` (Word),
pinned in `requirements.txt`.

## Finding the upload source (AL-8a)

`GET /api/v1/organizations/{organization_id}/upload-source`, for owners,
admins and members (viewers: 403): the organization's upload connection
(`id`, `name`, `status`, `last_synced_at`, `last_error`), or 404 when no
owner or admin has created it yet. Members need it because they cannot
list connections; the database already lets them see upload connections
of their own organization (policy `data_connections_member_upload_policy`).
