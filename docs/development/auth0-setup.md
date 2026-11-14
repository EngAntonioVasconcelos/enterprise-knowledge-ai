# Auth0 setup

The backend accepts Auth0 access tokens signed with RS256 and creates the
user's account on the first request, if the identity provider verified the
e-mail address. This page lists what must be configured in Auth0. It contains
no secrets.

## API

1. Create an API in Auth0 (Applications > APIs).
2. Its identifier is the audience: put it in `OIDC_AUDIENCE`.
3. Signing algorithm: RS256.

Backend settings (`backend/.env`, never committed):

| Setting | Value |
| --- | --- |
| `OIDC_ISSUER` | `https://<tenant>.<region>.auth0.com/` (with the final slash) |
| `OIDC_AUDIENCE` | The API identifier |
| `OIDC_JWKS_URL` | `https://<tenant>.<region>.auth0.com/.well-known/jwks.json` |
| `OIDC_CLAIMS_NAMESPACE` | `https://enterprise-knowledge-ai/` |

## Profile claims in the access token

Auth0 access tokens do not carry the e-mail by default. A post-login Action
adds it under a namespace, so the backend can create the account without an
extra call to Auth0 on every request.

Actions > Library > Create Action (trigger: Login / Post Login):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://enterprise-knowledge-ai/";

  api.accessToken.setCustomClaim(namespace + "email", event.user.email);
  api.accessToken.setCustomClaim(
    namespace + "email_verified",
    event.user.email_verified === true
  );
  api.accessToken.setCustomClaim(namespace + "name", event.user.name);
};
```

Deploy it and add it to the Login flow.

## Rules the backend applies

- No verified e-mail: `403`, and nothing is created.
- First login of a verified identity: the account and the identity are
  created by `app_private.provision_user`.
- A new identity (for example Google after a password login) with the same
  verified e-mail is linked to the existing account. Linking happens by
  verified e-mail only.
- A disabled account or identity: `401`.
- Signing up creates an account, not a membership: the person sees no
  organization until they create one or accept an invitation.
