# Organization dashboard (AK-7)

Owners and admins see the last 30 days in numbers. The dashboard never
shows who asked or what they asked.

## Where the numbers come from

Each answer writes one row in `answer_events` (migration `f2c7a9e4b6d1`):

| Kept | Not kept |
|---|---|
| the day (set by the database, no time of day) | who asked |
| whether there was a safe answer, and if it was verified | the question |
| the language | the answer |
| the cited documents (at most 10) | |

The question history (AK-6) is never read for the dashboard: it stays
private to each person.

- Members write rows for their own organization and for today only; they
  cannot read them back (the insert returns nothing).
- Owners and admins read the rows of their organization (row-level
  security). Nobody changes or deletes a row.
- The worker deletes rows older than a year
  (`app_private.purge_old_answer_events()`, in the same hourly pass as the
  question history). The function returns only a count.
- Counting never costs the answer: a failure is logged (`eka.history`)
  and the answer is returned.

## What it shows

`GET /api/v1/organizations/{id}/dashboard/` (owners and admins):

- questions per day for 30 days, split into answered and "no safe answer";
- the share of "no safe answer", the clearest sign of a missing document;
- the 10 most cited documents, **only those the viewer can open** (read as
  the viewer, so a private document never appears by its title);
- the languages of the questions;
- documents by state (numbers only) and the number of active members.

Topics are not taken from the text of the questions: in a small team a
topic can tell who asked. The most cited documents show what people look
for without that risk.

## In the web app

The "Dashboard" screen, in the menu for owners and admins only. The chart
by day has a table view; the hover shows each day's numbers.

## Not yet

- Aggregation in SQL when organizations grow large (it runs in Python on
  30 days of rows today).
- Hiding numbers for very small groups (k-anonymity), if a customer needs
  it.

## Gaps (Phase 7, AL-3)

The Gaps screen (`/lacunas`, owners and admins) says why questions of the
last 30 days got no safe answer, and in which documents people looked. It
answers "what should we write or fix?" without showing who asked or what.

Migration `c3f9a1e7d2b4` adds two columns to `answer_events`, filled only
for "no reliable answer":

- `gap_reason`: `no_sources` (nothing the person may read matched),
  `not_found` (documents read, the model found no answer), `checks` (the
  citation or number checks refused the text), `not_relevant` (the
  relevance check of AL-2 said it answered another question). The database
  refuses a reason on an answered question and any other value.
- `consulted_document_ids`: the documents given to the model, ids only, at
  most 10.

Rows written before the migration have no reason and are not counted, so
for the first 30 days the Gaps total can be lower than the Dashboard's.
Access (RLS), grants and the one-year purge are those of AK-7.

`GET /organizations/{id}/dashboard/gaps` returns totals only:

- the count per reason;
- the documents read by at least 3 questions without a safe answer in 30
  days (`GAP_MIN_QUESTIONS`): in a small team, one question on one subject
  can tell who asked; no day per document for the same reason;
- only documents the viewer can open are named; the others are counted in
  `hidden_documents`, never by title.

The Dashboard's "no safe answer" hint links to the Gaps screen.
