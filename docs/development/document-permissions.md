# Document permissions (Permission-aware AI)

A person sees, searches and gets answers only from documents they could
open at the source. This applies to owners and admins too (decision of
2026-11-15): even a title can reveal too much, so managers get counts per
status, not titles. Migration `a2d7c4e9f1b6`.

## Two tables

| Table | What | Written by |
|---|---|---|
| `document_permissions` | the source's permissions, as reported (user, group, domain, anyone, organization) | the worker, replaced at each sync |
| `document_access` | resolved readers: which platform users may read each document | database functions only |

Every read of `documents` and `document_versions` by the API is filtered by
`document_access` in row-level security, inside the query. Indexed passages
(Phase 6) will be filtered the same way, so the search itself never returns
what the caller may not read.

## How permissions resolve

A permission lets in an active member of the document's organization when:

| Principal | Rule |
|---|---|
| `user` | the member's verified e-mail equals it |
| `domain` | the member's e-mail domain equals it |
| `organization` | always (used by uploads shared with the organization) |
| `anyone` (link sharing) | only if the connection setting `link_sharing_grants_organization` is true |
| `group` | never, until group membership is synchronized |

Fail closed: anything unknown gives no access. Someone outside the
organization never gets access, whatever their e-mail.

## When access changes

| Event | Effect |
|---|---|
| sync reports new permissions | `replace_document_permissions` stores them and resolves readers |
| a member leaves (deactivated) | trigger removes all their access in that organization at once |
| a member joins or comes back | trigger grants what stored permissions allow |
| an admin changes `link_sharing_grants_organization` | trigger re-resolves the connection's documents |

## API

Under `/api/v1/organizations/{organization_id}/documents`:

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/` | any member | the documents the caller may read |
| GET | `/{id}` | any member | one of them; not found and not allowed look the same |
| GET | `/statistics` | owners, admins | `{"total", "by_status"}`, no titles |
