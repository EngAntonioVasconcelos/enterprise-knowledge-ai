# The web app (Phase 6, AK)

## What it is for

People ask questions about their company's documents and get an answer
they can check: every claim cites the passage it came from. The first
screen is the Assistant; other screens (sources, people, settings) are
added only when they exist, never as empty menu entries.

## Architecture

- **Next.js 16 (App Router), React 19, TypeScript in strict mode**, in
  `frontend/`. Server components render pages; client components only where
  the person interacts (the composer, the answer, the organization switch).
- **Backend for frontend.** The browser never talks to the backend API and
  never holds an access token. Auth0 keeps the session in an encrypted,
  http-only cookie (`@auth0/nextjs-auth0` v4); the Next.js server adds the
  person's token when it calls the backend (`src/lib/backend.ts`). The only
  route the browser can call is `POST /api/answers`, which checks its input
  before forwarding it.
- **`src/proxy.ts`** (Next.js 16's middleware) runs on every request: Auth0
  handles `/auth/login`, `/auth/callback` and `/auth/logout`, and every page
  but the entry page needs a session.
- **Three interface languages**: European Portuguese with "tu"
  (`src/i18n/pt-PT.ts`, the reference), English (`en.ts`) and French with
  "vous" (`fr.ts`). Every word the interface shows lives there; the other
  files are typed against the Portuguese one, so a missing key fails the
  build, and a test checks that no word is empty. Files are kept ASCII, so
  accents are written as escapes such as `\u00e9`.
  - The language is the person's choice, kept in the `eka_locale` cookie
    (one year, http-only) by a server action; without a choice, the
    browser's languages decide; otherwise European Portuguese.
  - No URL prefix (`/en/...`): the signed-in app is not indexed, so the
    language is a setting, not an address. `<html lang>` follows it.
  - The switch (rail and entry page) names each language in itself
    (Portugu\u00eas, English, Fran\u00e7ais) and has no flags: flags are
    countries, not languages.
  - The answers follow the language of the question; the interface
    language is sent with each question (`language`, forwarded as
    `interface_language`) and decides only when the question does not
    show its own ("minimum password length"). The answer text is marked
    with its language (`lang`) for screen readers. See answers.md (AJ-4).
- **Security headers** on every page (no framing, no sniffing, strict
  referrer, no camera or microphone).
- **Tests**: Vitest and Testing Library (components, the citation parser,
  the `/api/answers` route with the backend and Auth0 mocked). `npm run check`
  runs lint, types, tests and the production build; CI runs it on every push.

## Design

The product's one job is trust: an answer is only as good as the passage
behind it. The design follows from that.

- **The answer is an annotated page, not a chat bubble.** The question is
  the title, the answer is set for reading (Literata, about 64 characters a
  line), and the cited passages sit in the margin, numbered because
  citations are a sequence. Pointing at a citation lights up its passage
  and the other way round. Sources that were consulted but not cited are
  listed apart, quieter.
- **Colour means something.** Cobalt ink on cool paper; cobalt marks
  evidence and nothing else. Green says "checked in the sources"; amber
  says "no safe answer". No gradients, no decorative shadows, no cards
  inside cards.
- **Type.** Schibsted Grotesk for the interface, Literata for reading
  answers and passages. Both are served from the app (Fontsource), so no
  request goes to a font provider.
- **Honest states.** While waiting, the screen says what it is doing and
  how long it has taken; it does not pretend to stream. An unavailable
  model, a lost session and a bad question each get their own message and
  next step. "No safe answer" is shown as a result, not as an error.
- **Errors are not empty states.** If the backend refuses the request
  (401: the session; 403: the e-mail is not confirmed; other: the service),
  the page says so and offers the way out. "No organization" is shown only
  when the backend answered and the person really has none.
- **The first organization.** A new account with no organization sees one
  field, the organization's name; the technical name (slug) is made from it
  ("Atl\u00e2ntico Seguros" becomes `atlantico-seguros`) and gets a short
  random ending if it is taken. The person becomes its owner. A note says
  to ask for an invitation instead when the company already uses the
  product.
- **Documents.** One screen lists the documents the person can read, with
  their state in plain words (queued, reading, ready, could not be read),
  and refreshes itself while something is being read. Owners and
  administrators add files by dragging them or choosing them (PDF, Word
  .docx, text; 20 MB each, checked in the browser first). The upload source
  ("Uploaded files", a `file_upload` connection) is created on the first
  upload: nobody sets up a "connection" to send a PDF. Files go one per
  request through `POST /api/uploads` (the proxy allows 21 MB). Members and
  viewers see the list only, for now: they cannot list connections, so they
  cannot find the upload source.
- **People (AK-5).** Owners and administrators get a "People" screen
  (the menu shows it only to them: the list of organizations now carries
  the person's own `role`). It lists the active members, with their role,
  and the invitations not yet accepted. One form invites by e-mail with a
  role; the line under it says what the chosen role can do. An admin can
  give only member and viewer, and cannot change owners or admins (the
  backend's rule; the screen just does not offer it). Your own row has no
  actions, so nobody locks themselves out. Removing asks first, in the row;
  a role change applies at once and goes back if the backend refuses it
  (for example, the last owner).
- **Invitations.** The link is `/invitations/accept#token=...`. The token
  is after `#`, so it never reaches a server log; the page reads it in the
  browser, keeps it in this tab (`sessionStorage`) and takes it out of the
  address. Without a session it sends the person to sign in and back
  (`/auth/login?returnTo=/invitations/accept`); with one it shows the
  account that will accept and one button. Wrong e-mail, expired or used,
  and already a member each get their own message. While the server does
  not deliver e-mails (`EMAIL_SENDER=console`), the backend returns the
  token once and the People screen shows the link to copy and pass on.
- **Account photo.** The rail shows the photo of the sign-in (the
  `picture` claim from Google or Auth0), or the initials when there is
  none or it fails to load. Nothing is uploaded or stored by us. Other
  people's rows show initials.
- **History and settings (AK-6).** Everyone has a History screen with
  their own questions (nobody else sees them, admins included); an old
  answer is hidden when a cited document is no longer readable, and "Ask
  again" asks it at once. Owners and admins have Settings: the
  organization's name and how long questions are kept (0, 30, 90 or 365
  days). See question-history.md.
- **Dashboard (AK-7).** Owners and admins see the last 30 days in
  numbers: questions per day (answered and "no safe answer"), the most
  cited documents they can open, languages, documents and members. Never
  who asked or what. See dashboard.md.
- **The frame (design pass, AL-1b).** On wide screens a rail that stays in
  place while the page scrolls: the product mark and name; the organization
  being worked in (monogram, name and the person's role, and the switch
  when there is more than one, staying on the same screen); the screens
  with icons, management screens in their own group; and the account menu
  (photo or initials, name, e-mail, interface language, sign out). On small
  screens the same in a top bar, with the screens as a row that scrolls.
  Every page uses the same content width (72rem, centred), so the left edge
  does not jump between screens. A "skip to content" link comes first for
  keyboards. The assistant greets the person by first name and lists their
  five latest questions, which open from the history.
- **Quality floor.** Keyboard first (Enter asks, Shift+Enter breaks a
  line, visible focus), screen-reader labels and live regions, works down
  to a phone, and the only self-running motion stops for people who ask
  for less motion.

## Running it (development)

1. In Auth0, create a **Regular Web Application** for the web app:
   - Allowed Callback URLs: `http://localhost:3000/auth/callback`
   - Allowed Logout URLs: `http://localhost:3000`
   - The API it asks tokens for is the backend's: `AUTH0_AUDIENCE` equals
     `OIDC_AUDIENCE` in `backend/.env`.
2. Create `frontend/.env.local` from `frontend/.env.example` (never
   committed).
3. Start the API and the web app (from the repository root):

        docker compose -f infrastructure/dev/docker-compose.yml --profile app up --build

   Then open http://localhost:3000. The development database must be
   running, and Ollama for answers.

Checks, as blocks run them:

    docker compose -f infrastructure/dev/docker-compose.yml run --rm --no-deps frontend npm run check

## Answers from databases (AL-4b)

When an answer comes from a database (`data` in the answer, see
`data-gateway.md`), the margin shows the rows read instead of passages:
the connection's name, how many rows, the rows as a table (empty values
say so) and, folded, the read-only query that ran. The `[D1]` citation is
a small database mark that lights the rows up, as a number lights up its
passage. A refused answer never shows rows. The margin keeps at least
18rem on wide screens, so the table stays readable next to the text.
Numbers in the table are written as in the interface's language and
aligned to the right; codes with a leading zero and text stay as they
came (AL-6, `lib/data-cells.ts`).

## Databases in the settings (AL-7)

Owners and admins connect a PostgreSQL database in **Definicoes ->
Bases de dados** (`components/settings/DatabasesPanel.tsx`), instead of
the development script. The form asks for the name, server, port,
database, schemas, encryption, user and password, and says to use a login
that can only read. Connecting is three calls to the API
(`docs/development/postgresql-connector.md`): create the connection, seal
the login (sent once, never returned, never in the settings), and ask the
worker to read the tables. If the login cannot be stored, the new
connection is disconnected again, so no connection is left without one.

Each database shows where it is, how many tables were read and when, or
why they could not be read. "Ver tabelas" lists the tables and columns
the assistant may query: names only, never rows. While the tables are
being read the page looks again every 4 s, for about a minute.
"Desligar" asks first, in the page: disconnecting is final.

## Files sent by members (AL-8a)

Owners, admins and members send files in **Documentos**; viewers only
read. Before sending, the person chooses who can see the files: **Toda a
organizacao** or **So eu**. Members start on "So eu", so sharing with
everyone is a choice they make; owners and admins start on the whole
organization. The choice goes to the backend as `visibility`
(`organization` or `private`), and a file sent without one stays private.
Members cannot list connections, so the upload route asks
`GET /organizations/{id}/upload-source` for where files go; if no owner
or admin has sent the first file yet, it says so (`noSource`). A member
sees their own files waiting to be read, never anyone else's.

The third choice, **Pessoas escolhidas** (AL-8b), lists the active
colleagues from the directory (names and roles, no e-mail), with a search
box past eight people. Nothing is sent until at least one person is
chosen; the route refuses an empty or malformed choice (`noReaders`)
before calling the backend.

## Document page (AL-10)

Each document in Documentos links to `/documentos/<id>`
(`components/documents/DocumentPageView.tsx`): type, source, who sees it,
status, when it was last read, why the last reading failed, and "Como o
assistente o leu", the first passages the assistant answers from, so a
badly read file is noticed. Files still waiting to be read have no page
yet. A document the person cannot open shows "Documento nao encontrado",
the same as one that never existed.

## The Bancada frame (redesign, part 1)

The signed-in frame is the "Bancada" (workbench) design, chosen on the
design canvas: an 80 px dark rail on wide screens with the screens (each
icon with its name under it, so nothing has to be guessed) and the
account, a top bar with the organization being worked in and the command
bar, and the content in the rest. Small screens keep one top bar with the
screens in a scrolling row.

The command bar (`components/shell/CommandPalette.tsx`) opens with Ctrl+K
(Cmd+K on a Mac) or its button: type a question and Enter asks the
assistant; or go to a screen; or switch organization. It lists only what
the person may open, as the navigation does, and ignores accents
("ferias" finds "Ferias").

Tokens (`globals.css`): ink and graphite on a cool grey (`paper`
#eef0ef), the dark `rail`, and one accent, `signal` (petrol #0b5f58,
renamed from `cobalt`), which means evidence and the current place,
nothing else. Interface type is Atkinson Hyperlegible Next, chosen for
legibility; answers stay in Literata.

## The assistant bench (redesign, part 2)

On wide screens the assistant is a bench of two columns. On the left, the
question and the answer, with the earlier questions of the conversation
above and the question box held at the bottom of the screen, with the
count of questions and "New conversation" under it. On the right,
"Evidence": the passages or the rows of data behind the answer, always in
view while the answer is read. Pointing at or focusing a mark in the
answer (D1, a passage number) lights the matching piece of evidence, and
the other way round; the state lives in `AssistantView`.

`AnswerDocument.tsx` now exports the two halves, `AnswerText` and
`AnswerEvidence`, besides the whole `AnswerDocument`, which the history
keeps. Before an answer the pane says what will appear there; while
asking, that it is searching; with no evidence, that none was used. It
ends with the reminder that only evidence the person can open is shown.
Small screens show the same two parts one after the other.

## Documents (redesign, part 3)

The list is the screen: a search by name (accents and case do not matter),
the states as one row of choices with their counts (All, Ready, Reading,
Failed; a state with nothing in it is not shown), the source when there is
more than one, and the count of what is shown. When nothing matches, one
button clears the filters.

"Add files" opens a side panel (`AddFilesPanel.tsx`, a Radix dialog: focus
stays inside, Esc closes) with who can see the files, the place to drop or
choose them, and, for owners and admins, the sources (Google Drive).

A file whose name is already in the list is not sent at once. The panel
asks, for each one: Replace, Keep both or Don't send. Replace is offered
only for the person's own files (`ownFiles`, all their uploads, read or
not) and is chosen by default; for someone else's file, Keep both is. To
replace, the new file is sent first and only then is the old one taken
out (`DELETE /api/uploads`, a JSON body so another site cannot send it in
the person's name; the backend only finds files the caller sent). If the
old one cannot be taken out, the person is told that both are kept.

## History and one rule for buttons (redesign, part 4)

The history groups questions under the day they were asked ("Today",
"Yesterday", then the date) and shows only the time on each row. With six
questions or more, a search box finds them (accents and case do not
matter); when some had no safe answer, one choice shows only those, to ask
them again. The page passes the time it was made (`now`), so "Today" is
the same on the server and in the browser.

The other screens (Dashboard, Gaps, People, Settings, the entry page)
already use the Bancada tokens and layout, and stay as they are.

One rule for buttons: the main action of a screen is ink (`bg-ink`,
darkening to `signal-deep` on hover); `signal` keeps its one meaning,
evidence and the current place. "Add files" and "Continue" now follow it.
