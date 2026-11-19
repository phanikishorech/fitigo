"""Bounded internal source handoff worker. Never performs financial posting."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database.session import SessionLocal
from app.services.source_outbox import claim, finish


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['test','live'])
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--authorization-reference',required=True,help='Explicit approved worker-run authorization; not a gate toggle')
    args=parser.parse_args()
    from app.core.config import settings
    from app.database.session import engine
    from app.services.financial_startup import validate_configuration,validate_worker_request
    validate_worker_request(settings,args.mode,args.authorization_reference,allocations=False)
    validate_configuration(settings,engine)
    if not 1<=args.limit<=10000: parser.error('Limit must be 1..10000.')
    count=0
    for _ in range(args.limit):
        with SessionLocal() as db:
            lease=claim(db,args.mode);db.commit()
        if lease is None: break
        try:
            with SessionLocal() as db:
                finish(db,*lease,args.mode);db.commit()
            count+=1
        except Exception:
            # A process crash leaves an expiring lease. A controlled failure
            # records a redacted retry code in a separate transaction.
            with SessionLocal() as db:
                finish(db,*lease,args.mode,error_code='RETRY');db.commit()
            raise
    print(f'{count} source events retained awaiting policy/evidence; no posting performed.')


if __name__=='__main__': main()