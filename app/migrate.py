from app.database import engine
from app.migrations import run_migrations
from app.models import Base

Base.metadata.create_all(bind=engine)
run_migrations(engine)
print("Database ready")
