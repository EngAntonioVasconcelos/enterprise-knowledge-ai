# Connection scope (Admins can only narrow)

Owners and Admins can narrow what a connection brings in and who uses it.
They can never widen what the source allows: a person reads a document
when the source allows it AND the scope lets their role in (strict option,
decision of 15 Nov 2026; ADR-003).

## Setting it

The scope lives in the connection's settings
(`PATCH /organizations/{id}/connections/{connection_id}`):

    {"settings": {"scope": {
        "roles": ["owner", "admin", "member"],
        "file_types": ["pdf", "word", "google_docs"]
    }}}

- `roles`: owner, admin, member, viewer. Missing means every role.
- `file_types`: pdf, word, text (also Markdown), google_docs,
  google_slides. Missing means every supported type.
- Anything else is refused (422). PATCH replaces all settings, so send
  the other keys too (for example `link_sharing_grants_organization`).

## How it is enforced

- Roles: by the database, when it resolves who may read each document
  (migration e7c3a9f5b2d8). Changing the scope, or a person's role, takes
  effect at once, without a sync. Every read of documents and versions
  is filtered by it (RLS), retrieval and answers included.
- File types: by the sync engine. Excluded files are not downloaded or
  read, and leave retrieval if they were in. Changing the filter makes the
  next sync list the whole source again, so newly allowed files come in.
- Uploads: a member whose role is outside the scope cannot upload to that
  connection (403), and excluded types are refused at upload (415).

## Still to come

- Folders to include or exclude (Google Drive, SharePoint): needs the
  folder tree, built with the next connectors.
- Teams inside an organization (for example Finance): needs teams, which
  do not exist yet. Groups synchronized from the source (Drive groups)
  come with group membership sync.
