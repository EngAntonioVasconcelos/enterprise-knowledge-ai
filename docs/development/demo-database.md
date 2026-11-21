# The demo sales database (Phase 7, AL-4c)

A customer database with invented data, to see the agent answer from rows
on this computer. It is what a customer would connect, but local and
throwaway.

| | |
|---|---|
| Container | `eka-demo-sales` (`infrastructure/demo-db`) |
| Address | `127.0.0.1:1995`, database `sales`; from the containers `host.docker.internal:1995` |
| Data | In memory, created on every start by `init/01_sales.sql`: 40 customers (region, segment) and 240 invoices from June to November 2026 (amount without VAT, status paga, pendente or anulada) |
| Login for us | `eka_reader`: SELECT on `sales` only, and read-only by default |

Local ports in use: 1995 this demo database, 1996 development, 1998 the
owner-recovery test database, 1999 the test database.

The passwords in the compose file and in the script are for this local
database only. It accepts connections from this computer only.

## Start and connect

From the backend folder:

    docker compose -f ../infrastructure/demo-db/docker-compose.yml up -d --wait
    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.create_demo_connection

The script needs `DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS=true` in
`backend/.env` (development only: the demo database is on a private
address and has no TLS). It refuses any database but the development one
(port 1996). As the organization's owner, through the API's services and
row-level security, it creates the connection "Vendas (exemplo)", seals
its credentials and queues the catalog. With more than one organization,
add `--organization "name or slug"`.

The API, the worker and the data gateway read `.env` when they start:
restart them after changing it.

## Questions to try

(Written here without accents; ask them as you would.)

- Quanto faturamos por regiao em outubro?
- Quantas faturas estao pendentes?
- Quais sao os 5 clientes com mais faturacao?
- Quantos clientes particulares temos no Algarve?

A question the rows cannot answer, or a query the model gets wrong, must
end in "no reliable answer", never in an invented number.

## Stop

    docker compose -f ../infrastructure/demo-db/docker-compose.yml down

The data goes with the container. The connection stays in the development
database and goes to `error` until the demo database runs again.

## Measure the data tool (AL-4f)

    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.evaluate_data_answers

Eight fixed questions through the real agent, as the organization's owner,
with the configured model and the data gateway: six about the sales data
(expected numbers checked), one about documents (must not use the data)
and one the data cannot answer (must end with no answer). For each one it
prints the query the model wrote, the database's error, the rows read, the
model's raw replies (query, repair, answer, relevance) and the answer or
the refused draft, then the score and the time per question.

It prints what the product never logs, so it refuses anything but the
development database and gives the agent only the "Vendas (exemplo)"
connection, whose data is invented. It writes nothing: no history, no
dashboard counts, no audit. Use it to measure a prompt change: run it
before and after, with the same model, and keep the change only if the
score goes up and nothing else gets worse.

### Results

| Version | Correct | Wrong answers shown | Time per question |
|---|---|---|---|
| AL-4f (21 Nov, gemma3:4b) | 3 of 8 | 1 (the holiday question answered from invoices) | 25.7 s |
| AL-4g (21 Nov, gemma3:4b) | 4 of 8 (rule: 5) | 0 | 26.5 s |
| AL-4h (21 Nov, gemma3:4b) | 8 of 8 | 0 | 28.6 s |

AL-4g changes, after reading every reply of that run:

- the catalog shows each column's comment, so the model sees that
  `status` holds `paga, pendente or anulada` and `segment` holds
  `Empresa or Particular` (three failures came from guessing values:
  'pending', 'Anulada', and no filter for private customers);
- a separate first step (prompt `data_route_v1`) chooses DATA or
  DOCUMENTS, one word, documents when in doubt: asked together with
  writing the query, the model wrote SQL for the holiday question;
- the answer prompt v2 asks for the values with their labels and no
  sentences about what it does not know; an answer that only says
  "nao sei" is no answer;
- the data path costs 4 steps (choice, query, answer, check), so with the
  default budget a refused query is no longer repaired (5 steps).

Rule, fixed before measuring AL-4g: 0 wrong answers shown, at least 5 of
8 correct, none of questions 3, 5 and 8 lost, at most 35 s per question.
If it fails, AL-4g is not merged.

AL-4g did not pass its rule (4 of 8, question 3 lost) and was kept off
main. What failed: a stray semicolon before `LIMIT 50` (questions 2 and
4, with otherwise right SQL), an alias error that the repair used to fix
but no longer had room for with 4 steps (question 3), and "Nao sei [D1]"
next to a right count (question 6).

AL-4h, on top of AL-4g:

- a semicolon outside quotes followed only by `LIMIT n` is removed before
  the query is sent (`tidy_sql`); anything else is sent as written and the
  gateway still refuses a second statement;
- the answer prompt v3 gives three examples on other subjects, one of them
  a single count;
- the default budget goes from 4 to 5 steps (migration `e9c4a7b2d6f1`;
  organizations still on 4 move to 5, other values are kept), so the
  repair fits again.

Rule, fixed before measuring AL-4h: 0 wrong answers shown, at least 6 of
8 correct, questions 1, 5, 7 and 8 kept, at most 35 s per question. If it
passes, AL-4g and AL-4h are merged together; if not, neither is.

### AL-6: answers people read

- Numbers that are whole values of the rows are written as in the answer's
  language after the checks (19209.94: "19 209,94" in Portuguese and
  French, "19,209.94" in English); codes such as "Cliente 018" and years
  stay as they are. The table in the margin does the same.
- The answer prompt v4 was to state facts instead of addressing the person
  ("Ha 55 faturas pendentes", not "Tens 55 faturas"); the evaluation
  counts data answers that address the person.

Rule, fixed before measuring AL-6: 0 wrong answers shown, at least 7 of
8 correct, 0 data answers that address the person, at most 35 s per
question.

Result (21 Nov, gemma3:4b): 8 of 8 correct, 0 wrong answers shown, but 6
data answers still address the person ("Tens 55 faturas", "Tu tens os
seguintes clientes"; the count said 5, missing "Tu tens") and 52.6 s per
question (28.6 s with AL-4h, with the same steps: the computer was busy
rebuilding the web app). The prompt v4 did not pass and was dropped: the
answers use v3 again. The number formatting is code, not a prompt, and
stays. The product addresses the person as "tu" everywhere ("os
documentos a que tens acesso"), so "Tens 55 faturas" is clumsy, not wrong;
it is measured again with the hosted model (Phase 8).
