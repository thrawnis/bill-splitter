#!/bin/bash
set -euo pipefail

mkdir -p /app/data/uploads
chown app:app /app/data /app/data/uploads

gosu app python -c "
from app.database import engine
from app.models import Base
Base.metadata.create_all(bind=engine)
print('Database ready')
"

exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
