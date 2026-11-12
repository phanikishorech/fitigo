"""Read-only local report; no network probes, messages, file cleanup or migrations."""
import json
from app.database.session import SessionLocal
from app.services.readiness_service import readiness


def main():
    if SessionLocal is None: raise RuntimeError('Database unavailable')
    with SessionLocal() as db:
        result = readiness(db)
    print(json.dumps(result, indent=2))
    return 2 if any(c['status'] == 'BLOCKED' for c in result['checks']) else 0


if __name__ == '__main__': raise SystemExit(main())