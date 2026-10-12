"""Vector column type: pgvector on PostgreSQL, JSON elsewhere (SQLite in local runs and tests)."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON

# No fixed dimension, so the embedding model can change without a schema migration. An ANN index needs a fixed
# dimension; add one per model with a migration when the corpus grows (docs/DATABASE.md).
VectorType = JSON().with_variant(Vector(), "postgresql")
