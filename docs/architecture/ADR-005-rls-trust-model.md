# ADR-005: Row-level security trust model ("Model A")
 
- Status: accepted
- Date: 2026-11-14
 
## Context
 
Enterprise Knowledge AI is multi-tenant. Every tenant table lives in one
PostgreSQL database. The application connects as one login role,
`eka_runtime`, for every user and every organization.
 
Row-level security (RLS) needs to know who is asking. PostgreSQL only knows
the login role, which is the same for everyone. The application therefore
passes the identity in transaction-local settings (GUCs):
 
| Setting | Set by | Meaning |
| --- | --- | --- |
| `app.auth_issuer`, `app.auth_subject` | `set_authentication_context` | Issuer and subject of a verified OIDC token |
| `app.user_id` | `set_identity_context` | Internal user resolved from that identity |
| `app.organization_id` | `set_organization_context` | Organization of the request, after an active membership is confirmed |
 
They are written with `set_config(..., true)`, so they end with the
transaction, and re-applied at the start of every transaction
(`app/db/context.py`).
 
## Decision
 
RLS protects the data against defects in the application, not against a
compromised application.
 
1. The database trusts the GUCs set by `eka_runtime`. It does not verify the
   token itself.
2. Every tenant table has `ENABLE` and `FORCE ROW LEVEL SECURITY`. With no
   context, queries return no rows and writes are refused.
3. Visibility checks live in `SECURITY DEFINER` functions in schema
   `app_private`, owned by `eka_rls_helper` (NOLOGIN, BYPASSRLS), with
   `search_path = pg_catalog` and `EXECUTE` revoked from `PUBLIC`.
4. Rules RLS cannot express (immutable columns, "one active owner") are
   triggers, which apply to every role.
5. `eka_runtime` is NOSUPERUSER and NOBYPASSRLS and holds only the table
   privileges it needs, granted explicitly by migrations.
6. Operations above any tenant (owner recovery, platform admin assignment)
   are not reachable by `eka_runtime`. They need a separate login holding
   `eka_platform_recovery`.
 
## What this protects against
 
- A query that forgets the tenant filter: it returns only the caller's rows.
- A route that forgets an authorization check: RLS still refuses rows of
  other organizations.
- A bug that writes to the wrong organization, changes a membership's
  organization or user, or removes the last owner: refused by policies and
  triggers.
- Reading accounts or login identities of other users.
 
## What this does not protect against
 
- Code execution or SQL injection inside the application process. Whoever
  controls `eka_runtime` can set any GUC and impersonate any user. A test
  (`test_model_a_documents_runtime_context_spoofing_limitation`)
  documents this.
- A leaked `eka_runtime` password. It must live only in the runtime secret
  store and be rotated on suspicion.
- Superuser or migration credentials, which bypass RLS. Migrations run as a
  superuser until a dedicated migration role exists (Phase 8).
 
## Consequences
 
- SQL injection is still critical. Queries go through SQLAlchemy with bound
  parameters; raw SQL with string formatting is forbidden.
- Every new tenant table must enable and force RLS in the migration that
  creates it, with integration tests for allowed and refused access.
- The agent acts as the user through the same context, so it inherits the
  same limits. It never gets a role that bypasses RLS.
- Integration tests must connect as `eka_runtime`; the test fixture refuses
  superuser and BYPASSRLS roles.
 
## Alternatives considered
 
- **One database role per user or per organization.** The database would
  verify identity itself, but roles are cluster-wide objects and do not scale
  to thousands of tenants; pooling becomes per role.
- **Verifying a signed token inside PostgreSQL.** Possible with an extension,
  but it moves key management into the database and still trusts the
  application to pass the token.
- **One database per tenant.** Strong isolation, but heavy operations
  (migrations, connections, backups) for a product that starts with many
  small organizations. It can be offered later to large customers.
 
Model A can be strengthened later without changing the schema, for example
by signing the context with a key the runtime cannot read.
