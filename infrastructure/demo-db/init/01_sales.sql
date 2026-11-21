-- Invented sales data for the agent's data tool (AL-4c). Deterministic:
-- the same rows on every start.

CREATE SCHEMA sales;
COMMENT ON SCHEMA sales IS 'Invented sales data for trying the agent';

CREATE TABLE sales.customers (
    id integer PRIMARY KEY,
    name text NOT NULL,
    region text NOT NULL,
    segment text NOT NULL
);
COMMENT ON TABLE sales.customers IS 'One row per customer';
COMMENT ON COLUMN sales.customers.region IS 'Lisboa, Norte, Centro, Alentejo or Algarve';
COMMENT ON COLUMN sales.customers.segment IS 'Empresa or Particular';

CREATE TABLE sales.invoices (
    id integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES sales.customers (id),
    issued_on date NOT NULL,
    amount numeric(10, 2) NOT NULL,
    status text NOT NULL
);
COMMENT ON TABLE sales.invoices IS 'One row per invoice, amounts in euros without VAT';
COMMENT ON COLUMN sales.invoices.status IS 'paga, pendente or anulada';

INSERT INTO sales.customers (id, name, region, segment)
SELECT
    n,
    'Cliente ' || lpad(n::text, 3, '0'),
    (ARRAY['Lisboa', 'Norte', 'Centro', 'Alentejo', 'Algarve'])[1 + (n * 7) % 5],
    CASE WHEN n % 3 = 0 THEN 'Particular' ELSE 'Empresa' END
FROM generate_series(1, 40) AS n;

INSERT INTO sales.invoices (id, customer_id, issued_on, amount, status)
SELECT
    n,
    1 + (n * 13) % 40,
    date '2026-06-01' + ((n * 37) % 183),
    round((150 + (n * 7919) % 4850)::numeric + ((n * 31) % 100) / 100.0, 2),
    CASE WHEN n % 11 = 0 THEN 'anulada' WHEN n % 4 = 0 THEN 'pendente' ELSE 'paga' END
FROM generate_series(1, 240) AS n;

ANALYZE sales.customers;
ANALYZE sales.invoices;

-- What a customer should give us: a login that can only read these tables.
CREATE ROLE eka_reader LOGIN PASSWORD 'local-demo-reader-only'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE sales TO eka_reader;
GRANT USAGE ON SCHEMA sales TO eka_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO eka_reader;
ALTER ROLE eka_reader SET default_transaction_read_only = on;
