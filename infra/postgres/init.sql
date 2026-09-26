-- Bootstrap extensions the M4+ schema needs. No tables here (Alembic owns
-- migrations); this file only prepares the extension the base image lacks.
CREATE EXTENSION IF NOT EXISTS vector;

-- Dev/CI-only application role (M6-Persistence/Foundation, ADR-009 s20-21).
-- Role *existence* is bootstrapped here because CREATE ROLE is cluster-level
-- and Alembic should not need superuser to run a schema migration; the
-- role's actual table-level grants (and the memory_event append-only
-- REVOKEs) are owned by migrations/versions/0001_initial.py, not here -
-- this file only ensures the role exists for that migration to grant to.
-- The password below is dev-only, matching the POSTGRES_PASSWORD already
-- hardcoded for the superuser in docker-compose.dev.yml; a real deployment
-- provisions its own role/password via its own secrets tooling, never this
-- file (M6-Persistence/Foundation planning s4/s22).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mindtrace_app') THEN
    CREATE ROLE mindtrace_app LOGIN PASSWORD 'mindtrace_app_dev_only';
  END IF;
END
$$;
