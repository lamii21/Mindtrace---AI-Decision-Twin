-- Bootstrap extensions the M4+ schema needs. No tables here (Alembic owns
-- migrations); this file only prepares the extension the base image lacks.
CREATE EXTENSION IF NOT EXISTS vector;
