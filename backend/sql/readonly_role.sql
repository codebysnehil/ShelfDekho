-- Read-only role for the AI analyst (defence in depth on top of the SQL guard and the
-- READ ONLY transaction). Run once as the database owner, e.g. in Neon's SQL editor,
-- then set ANALYST_DATABASE_URL to a connection string for this role.
--
-- Replace the password before running.

CREATE ROLE shelfiq_analyst LOGIN PASSWORD 'change-me';

GRANT CONNECT ON DATABASE neondb TO shelfiq_analyst;  -- your database name
GRANT USAGE ON SCHEMA public TO shelfiq_analyst;
GRANT SELECT ON stores, products, daily_sales, promotions, inventory, forecasts
  TO shelfiq_analyst;

-- Cap runaway queries even if a client forgets to set a timeout.
ALTER ROLE shelfiq_analyst SET statement_timeout = '5s';
ALTER ROLE shelfiq_analyst SET default_transaction_read_only = on;
