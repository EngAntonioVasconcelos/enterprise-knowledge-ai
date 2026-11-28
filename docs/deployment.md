# Deployment (Phase 10a): the public demo on one server

One Linux server with Docker runs everything: `infrastructure/prod/`.
The demo runs on an Oracle Cloud Always Free ARM machine in Frankfurt
(2 OCPUs, 12 GB, 100 GB, Ubuntu 24.04); the same files run on any server,
only `.env` changes.

## What runs

| Service | Role | Reachable from |
|---|---|---|
| caddy | HTTPS (Let's Encrypt), redirects HTTP | the internet, ports 80 and 443 |
| frontend | the web app (Next.js, production build) | caddy |
| api | the backend API | frontend |
| worker | reads files, computes vectors | nothing (polls the database) |
| data-gateway | the only process that queries customer databases | api |
| ollama | the local model, kept loaded in memory | api |
| postgres | PostgreSQL 18 with pgvector | the services above |
| migrate | one-off: roles and migrations | run by hand |

No port but 80 and 443 is published. Logs rotate (5 files of 10 MB per
service).

## Logins

| Login | Used by | Can do |
|---|---|---|
| eka_admin | migrate only | everything (owner of the database) |
| eka_runtime | api | what the policies allow, never BYPASSRLS |
| eka_worker_login | worker, data-gateway | only `SET ROLE eka_worker`; nothing before it |
| eka_mailer_login | the e-mail dispatcher (later) | only `SET ROLE eka_mailer` |

`scripts/bootstrap_service_logins.py` creates the two service logins after
the migrations (`NOINHERIT`, membership `WITH INHERIT FALSE, SET TRUE`).
Each service receives only the settings it needs: the API never sees the
master private key, the worker never sees the Auth0 secrets.

## Secrets

`infrastructure/prod/make-env.sh DOMAIN EMAIL` writes `.env` once, on the
server, readable only by its owner: random database passwords, internal
secrets and the master key pair (made by the app's own code). It prints
nothing secret and refuses to run when `.env` exists. The Auth0 values are
typed on the server with `nano .env`. `.env` is never committed, copied or
sent.

## First installation

On the server, in `~/eka` (a clone of the repository):

    cd ~/eka/infrastructure/prod
    sh make-env.sh 92-6-167-96.sslip.io you@example.com
    nano .env                                  # AUTH0_* and OIDC_*
    docker compose up -d postgres ollama
    docker compose run --rm migrate
    docker compose exec ollama ollama pull gemma3:4b
    docker compose up -d --build
    docker compose exec api python -m scripts.try_embeddings --model intfloat/multilingual-e5-base
    docker compose exec api python -m scripts.try_reranker
    docker compose restart api worker

Then open TCP 80 and 443 in the subnet's security list. In Auth0, the
application allows `https://DOMAIN/auth/callback` (callback),
`https://DOMAIN` (logout and web origin).

`sslip.io` turns the address into a name (`92-6-167-96.sslip.io` is
92.6.167.96), so Let's Encrypt can issue a certificate without buying a
domain. A real domain later only changes `EKA_DOMAIN`.

The API and the worker never download a model while they serve requests
(`local_files_only`), so the two search models are downloaded once into the
`eka_models` volume, which both share. Without them, search falls back to
words only: questions in another language than the document find nothing,
and the vector jobs (`document.embed`) fail. `try_embeddings` downloads
`multilingual-e5-small` unless `--model` names the configured one.

## Vectors missing

When `document.embed` jobs failed for good (the models were not there yet)
or `EMBEDDING_MODEL` changed, queue them again. The first command only
counts; `--apply` adds one job per document without vectors and changes
nothing else:

    docker compose --profile setup run --rm migrate python -m scripts.queue_missing_embeddings
    docker compose --profile setup run --rm migrate python -m scripts.queue_missing_embeddings --apply

## Updating

    cd ~/eka && git pull --ff-only
    cd infrastructure/prod
    docker compose build
    docker compose run --rm migrate
    docker compose up -d

## Why the model stays loaded

Oracle may stop Always Free instances that stay below 20% CPU, network
and memory for 7 days. With the model kept in memory (`OLLAMA_KEEP_ALIVE=-1`)
and the embedding models loaded by the API and the worker, memory use
stays well above that, and the first answer does not wait for the model to
load.

## Not yet (rest of Phase 10)

Backups with a tested restore, e-mail delivery, monitoring, the fictional
company's documents and sales database, and invitation-only access.
