"""Schedule at least once a minute after deploying the funding migration."""
import json
from app.database.session import SessionLocal
from app.services.wallet_hold_recovery import recover_due

if __name__ == '__main__':
    if SessionLocal is None: raise SystemExit('Database is not configured.')
    with SessionLocal() as db: print(json.dumps(recover_due(db)))