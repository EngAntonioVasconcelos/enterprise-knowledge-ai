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
