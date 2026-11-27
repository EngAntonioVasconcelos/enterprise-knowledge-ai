#!/bin/sh
# Creates infrastructure/prod/.env on the server, once (Phase 10a).
#
#     sh make-env.sh DOMAIN EMAIL
#
# DOMAIN: where the app is served (e.g. 92-6-167-96.sslip.io).
# EMAIL: for Let's Encrypt notices about the certificate.
#
# Every password and key is random and written only to .env, which only
# its owner can read. Nothing secret is printed. It refuses to run when
# .env exists: new database passwords or a new master key would lock the
# app out of its own data.
set -eu
cd "$(dirname "$0")"

if [ -e .env ]; then
    echo "PAROU: .env already exists; nothing changed." >&2
    exit 1
fi
DOMAIN="${1:?usage: sh make-env.sh DOMAIN EMAIL}"
EMAIL="${2:?usage: sh make-env.sh DOMAIN EMAIL}"

umask 077
random() { openssl rand -hex 32; }

cat > .env <<ENV
# Created by make-env.sh. Never commit, copy or send this file.
EKA_DOMAIN=$DOMAIN
EKA_ACME_EMAIL=$EMAIL

# Database logins (random).
EKA_ADMIN_PASSWORD=$(random)
EKA_RUNTIME_PASSWORD=$(random)
EKA_WORKER_PASSWORD=$(random)
EKA_MAILER_PASSWORD=$(random)

# Internal secrets (random).
OAUTH_STATE_SECRET=$(random)
DATA_GATEWAY_TOKEN=$(random)
AUTH0_SECRET=$(random)

# The model and the answer prompt.
LLM_MODEL=gemma3:4b
ANSWER_PROMPT_VERSION=v3

# Fill in with "nano .env" (values from the Auth0 dashboard).
AUTH0_DOMAIN=
AUTH0_CLIENT_ID=
AUTH0_CLIENT_SECRET=
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
OIDC_CLAIMS_NAMESPACE=

# Optional: Google Drive (empty = not offered).
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
ENV

# The master key for stored connection credentials, made by the app's own
# code in its image (the private key never leaves .env).
docker build -q -t eka-backend:prod ../../backend >/dev/null
docker run --rm --entrypoint python eka-backend:prod -c "
from app.core import credential_crypto as c
public, private = c.generate_key_pair()
print('CREDENTIALS_MASTER_PUBLIC_KEY=' + c.encode_key(public))
print('CREDENTIALS_MASTER_PRIVATE_KEY=' + c.encode_key(private))
" >> .env

chmod 600 .env
echo "Created .env (only you can read it). Next: nano .env, fill AUTH0_* and OIDC_*."
