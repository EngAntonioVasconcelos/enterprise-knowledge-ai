# Question history (AK-6)

Each person can go back to the questions they asked and the answers they
got. The history is personal: nobody else in the organization reads it,
owners and admins included.

## Rules

- **Only the person who asked reads an entry.** The database enforces it
  (row-level security on `question_history`, migration `e6b1d4a8c2f9`): the
  runtime role reads and deletes only rows whose `user_id` is the caller,
  in an organization the caller is still an active member of. Rows are
  never changed (no UPDATE privilege). Every query in
  `app/services/history_service.py` also filters by the caller.
- **An old answer never shows what the person can no longer see.** When an
  entry is opened, the cited documents are read again as that person. If a
  cited document was removed or the person lost access to it, the answer
  text is hidden (`hidden: true`) and the person is offered "Ask again".
  Sources the person can no longer read are left out. If a cited document
  has a newer version, the entry is marked `outdated`.
- **The organization decides how long entries are kept**:
  `organizations.history_retention_days`, one of 0 (keep nothing), 30, 90
  (default) or 365. Owners and admins change it in Settings; each change is
  recorded in the audit log (`organization.history_retention_changed`).
  With 0, nothing new is written (also refused by the database).
- **Old entries are deleted.** The worker calls
  `app_private.purge_expired_questions()` at start and then once an hour.
  The function deletes rows older than their organization's period and
  returns only a count: the worker cannot read the questions. Listing and
  opening also ignore entries past the period, so nothing expired is shown
  even if the worker is stopped.
- **People delete their own entries**, one by one or all at once.
- **A failure to keep the history never costs the answer**: the answer is
  returned and the failure is logged (`eka.history`, error class only).

## API

All under `/api/v1/organizations/{organization_id}/history`, for any
active member:

| Method | Path | What it does |
|---|---|---|
| GET | `/` | The caller's entries, newest first (`limit`, at most 100) |
| GET | `/{id}` | One entry, with its sources checked again |
| DELETE | `/{id}` | Deletes one entry (404 if it is not the caller's) |
| DELETE | `/` | Deletes all of the caller's entries |

`POST .../answers/` keeps each exchange while the organization keeps a
history. `PATCH /organizations/{id}` accepts `history_retention_days`.

## In the web app

- **History** (everyone): the list of the person's questions, the entry
  page with the answer as it was shown (or why it is hidden), "Ask again"
  (opens the assistant and asks at once; the question is then taken out of
  the address) and Delete; "Delete all history" asks first.
- **Settings** (owners and admins): the organization's name and how long
  questions are kept. Choosing a shorter period warns that older questions
  are deleted within the hour, for everyone.

## Not yet

- The organization logo (needs file storage and safe image handling).
- Search inside the history.
