# Import every model here so Alembic can discover them via Base.metadata.
from app.models.job_application import JobApplication  # noqa: F401
from app.models.resume import Resume  # noqa: F401
from app.models.user import User  # noqa: F401