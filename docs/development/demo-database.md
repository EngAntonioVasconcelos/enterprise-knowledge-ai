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
