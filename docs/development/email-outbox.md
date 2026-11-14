# E-mail outbox

Invitation e-mails are written to `email_outbox` in the same transaction as
the invitation, then sent by a separate dispatcher. Migration
`b3f8d2a6c9e4` sets this up.

## Who can do what

| Role | On `email_outbox` |
|---|---|
| `eka_runtime` (the API) | INSERT only, and only for a pending invitation of an organization it manages, to the invited address. It cannot read the outbox back. |
| `eka_mailer` (dispatcher) | SELECT, and UPDATE of `body`, `attempts`, `last_error`, `sent_at`, `cancelled_at`. Nothing else in the database. |
| triggers | A body can only be cleared, never rewritten. A sent or cancelled e-mail never changes. An invitation that stops being pending cancels its unsent e-mail. |

The body holds the one-time link, so it is cleared as soon as the e-mail is
sent, cancelled, given up after 5 attempts, or expires with its invitation.
The link carries the token in the URL fragment
(`/invitations/accept#token=...`), which browsers never send to a server.

## Running the dispatcher

`eka_mailer` cannot log in. The dispatcher connects with a login that holds
it and switches to it for every batch (`SET LOCAL ROLE eka_mailer`), so it
gets the mailer's privileges and nothing more.

Settings (names only; values stay in your `.env`):

- `MAILER_DATABASE_URL`: the dispatcher's login.
- `EMAIL_SENDER`: `console` for now. It prints the message, link included,
  and must never be used in production.
- `EMAIL_FROM`: the From address.
- `FRONTEND_BASE_URL`: where the accept page lives.

From the backend folder:

```
python -m scripts.send_outbox_emails            # one batch
python -m scripts.send_outbox_emails --watch    # keep polling
```

Delivery is at least once: if the process stops between sending and
committing, that e-mail is sent again.

The dedicated login is created by an operator, with approval, when the
dispatcher is deployed. In development the migration login can be used,
since a superuser is a member of every role.

## Still open

- The real provider (SES in the EU, Brevo or Postmark) is chosen with
  hosting, in Phase 8. It only needs a new `EmailSender`.
- The API returns the invitation token only while a development sender
  (`console`) is configured. With a real provider it returns no token:
  the link reaches the invitee alone, by e-mail.
