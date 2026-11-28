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

## Backups

`backup.sh` copies the database (`pg_dump`, custom format) and the uploaded
files (`eka_storage`) every day at 03:17. One copy stays on the server in
`~/eka-backups` for 7 days; one goes to the Oracle Object Storage bucket
`eka-backups`, whose lifecycle rule deletes objects older than 30 days.
The models and the certificate are not copied: they come back on their own.
`.env` stays only on the server; if the server is lost, new secrets are
generated and only encrypted connector credentials have to be entered again.

The upload uses a pre-authenticated request of the bucket that only permits
object writes, so this server cannot read or delete the copies. Its URL is
kept in `infrastructure/prod/backup.par` (chmod 600, ignored by Git) and is
never printed. Without that file the copy stays only on the server.

    sh backup.sh                       # one backup now
    sh restore-check.sh                # restore the last one into eka_restore_check, compare, remove it
    crontab -e                         # 17 3 * * * cd $HOME/eka/infrastructure/prod && sh backup.sh >> $HOME/eka-backups/backup.log 2>&1

To restore for real, stop the api and the worker, restore the dump into a
new database, check it with the same counts and only then switch `eka`.

## Monitoring

An outside service (Better Stack) watches the demo, so an alert still goes
out when the server itself is down:

- `https://DOMAIN/` answers (the site and its certificate);
- `https://DOMAIN/health` answers 200: the frontend asked the API, and the
  API asked the database (`/health/ready`). It needs no session and shows
  nothing about the inside;
- a heartbeat: `backup.sh` calls the URL kept in
  `infrastructure/prod/backup.heartbeat` (chmod 600, ignored by Git) after
  a full backup. When a day passes without it, the monitor sends an e-mail.

## Not yet (rest of Phase 10)

E-mail delivery and the fictional company's sales database.
