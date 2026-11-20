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
  - The interface language does not yet change the language of the
    answers: the answer prompt (v3) writes European Portuguese. Answering
    in the interface language is a prompt change, measured like the others.
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
