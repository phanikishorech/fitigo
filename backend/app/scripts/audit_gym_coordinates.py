"""Read-only coordinate audit. Run before/after migration; never geocodes or writes."""
import json
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models.gym import Gym
from app.services.gym_geo import coordinates


def main():
    if SessionLocal is None:
        raise SystemExit('Database is not configured; no audit performed.')
    invalid = []
    total = 0
    with SessionLocal() as db:
        # Explicit legacy columns allow this audit before the projection migration.
        rows = db.execute(select(Gym.id, Gym.status, Gym.is_active, Gym.latitude, Gym.longitude)
                          .order_by(Gym.id).execution_options(yield_per=500))
        for gid, status, active, latitude, longitude in rows:
            total += 1
            if coordinates(latitude, longitude) is None:
                invalid.append({'gym_id': gid, 'status': status, 'is_active': active,
                                'discoverable_status': status == 'APPROVED' and active,
                                'issue': 'missing' if latitude is None or longitude is None else 'invalid'})
        db.rollback()
    print(json.dumps({'total_gyms': total, 'invalid_count': len(invalid), 'affected_gyms': invalid}, indent=2))


if __name__ == '__main__':
    main()