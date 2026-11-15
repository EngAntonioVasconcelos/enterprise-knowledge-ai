# Connection credentials

See ADR-007 for the design. In short: the API seals, only the worker opens.

## Setting up the development key (once)

From `backend`, with the `.venv` active:

```
python -m scripts.generate_master_key
```

It writes `CREDENTIALS_MASTER_PUBLIC_KEY` and
`CREDENTIALS_MASTER_PRIVATE_KEY` to `backend/.env` and prints only the
fingerprint. It refuses to run if a key is already there: replacing it
would make every stored credential unreadable. Never paste these values
into a chat or a commit.

Without the public key the API answers 503 to any request that stores a
secret; everything else works.

## API

Owners and admins, under
`/api/v1/organizations/{organization_id}/connections/{connection_id}`:

| Method | Path | What |
|---|---|---|
| PUT | `/credentials` | store or replace the secret: `{"secret": {...}}`, answers 204 with no body |
| GET | `/credentials` | `{"configured", "updated_at", "key"}`; never the secret |

## Who can do what

| Role | Keys and credentials |
|---|---|
| `eka_runtime` (the API) | insert and replace; read only whether they exist, their fingerprint and dates |
| `eka_worker` | read the sealed values of the organization of its current job |
| trigger | disconnecting a connection destroys its secret; every change is audited |

## In code

- `app/core/credential_crypto.py`: sealing and keys.
- `app/services/credential_service.py`: `store_credentials` and
  `credentials_status` (API), `load_credentials` (worker only).
