# Google Drive connector

A `google_drive` connection brings the documents a Google account can read
into the archive, with Drive's own sharing as permissions (ADR-003). It is
fed to the same sync engine as every source (`docs/development/sync.md`).

## What is read

- Google Docs and Google Slides, exported as text.
- PDF, Word (.docx), text and Markdown files, downloaded and read by the
  same extraction as uploads (`docs/development/uploads.md`), up to 20 MB.
- Google Sheets, Excel and CSV are not read here: tabular data is answered
  by queries (ADR-006), in the DuckDB item.

## How a sync works

- First sync: a change token is taken, then every supported, non-trashed
  file is listed (My Drive, shared with the account, shared drives). The
  listing is complete, so files that left the account leave retrieval. If
  Drive answers that the listing is incomplete, nothing is removed.
- Later syncs read only the Drive changes since the saved token. Removed,
  trashed or no-longer-supported files leave retrieval; nothing else is
  touched.
- A file whose revision (md5 or version) did not change is not downloaded.
- If Drive is busy (429, 5xx, rate limits), the sync stops, the token is
  not moved and the job is retried later. A single unreadable file
  (too large, export refused, gone) fails alone.

## Permissions

Drive permissions map to source permissions: user, group, domain and
anyone, with owner, writer (also organizer and file organizer), commenter
and reader. Deleted and unknown entries are skipped. When Drive does not
show a file's sharing to the connected account (it is not allowed to
share it), only the connected account is granted. Shared-drive files are
asked for their permissions one by one. Groups and "anyone with the link"
give no access by default (`docs/development/document-permissions.md`).

## Authorization (OAuth 2.0 with PKCE)

1. An Owner or Admin calls
   `POST /organizations/{id}/connections/{connection_id}/google/authorize`
   and opens the `authorization_url` it returns (valid 10 minutes, for that
   person and that connection only).
2. Google sends the browser to `GOOGLE_OAUTH_REDIRECT_URI` (by default
   `FRONTEND_BASE_URL/connections/google/callback`) with `code` and `state`.
3. The frontend posts both to `.../google/callback`. The server exchanges
   the code and seals the refresh token at once (ADR-007). The response
   only says that credentials are configured.

If Google later refuses the authorization (access removed in the Google
account), the connection goes to `error` and an admin authorizes again;
that puts it back to `active`.

## Setting up Google Cloud (free)

Standard use of the Drive API has no cost, and no billing account is
needed. Do not accept a billing or trial offer: it is not required.

1. https://console.cloud.google.com: create a project (for example
   `eka-dev`).
2. APIs and Services, Library: enable the Google Drive API.
3. Google Auth Platform (OAuth consent screen): user type External,
   app name, support e-mail; status Testing. Add your own Google account
   under Test users (up to 100).
4. Data access: add the scope `.../auth/drive.readonly`.
5. Clients: create an OAuth client of type Web application with the
   authorized redirect URI `http://localhost:3000/connections/google/callback`.
6. Put the client id and secret in `backend/.env` yourself
   (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`). Never paste
   them in a chat, a ticket or a commit.
7. Create the state secret: `python -m scripts.generate_state_secret`.

In Testing status, Google shows an "unverified app" warning and the
authorization lasts 7 days; both are expected in development.

## Before production

`drive.readonly` is a restricted scope. Publishing the app for everyone
requires Google's verification and a yearly security assessment (CASA),
which has a cost. The alternative is the non-restricted `drive.file` scope
with the Google Picker, where people choose the files and folders to share.
The connector code is the same for both (the scope is a setting,
`GOOGLE_DRIVE_SCOPE`); the choice is made before launch (Phase 10).
