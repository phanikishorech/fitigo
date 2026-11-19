"""Explicit source-event allocation, no historical scan, payouts or provider calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.session import SessionLocal
from app.models.source_evidence import SourceOutbox
from app.services.marketplace_allocations import allocate_event
from app.services.gym_visit_payouts import allocate_visit
from app.services.marketplace_calculation import AllocationBlocked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=['test','live'])
    parser.add_argument('--event-id',required=True,action='append',help='Explicit existing outbox UUID; repeat up to 100 times')
    parser.add_argument('--authorization-reference',required=True,help='Explicit approved worker-run authorization; not a gate toggle')
    args=parser.parse_args()
    from app.core.config import settings
    from app.database.session import engine
    from app.services.financial_startup import validate_configuration,validate_worker_request
    validate_worker_request(settings,args.mode,args.authorization_reference,allocations=True)
    validate_configuration(settings,engine)
    if len(args.event_id)>100:parser.error('At most 100 explicitly reviewed events.')
    failed=False
    for identifier in args.event_id:
        with SessionLocal() as db:
            try:
                event=db.get(SourceOutbox,identifier)
                if not event or event.mode!=args.mode:raise AllocationBlocked('ENVIRONMENT_MISMATCH','Source event not in requested environment.')
                result=allocate_visit(db,identifier) if event.event_type=='MULTI_GYM_VISIT_VERIFIED' else allocate_event(db,identifier)
                db.commit()
                print(json.dumps({'event_id':identifier,'status':'ALLOCATED','ids':[r.id for r in result] if isinstance(result,list) else [result.id]}))
            except AllocationBlocked as error:
                db.rollback();failed=True
                print(json.dumps({'event_id':identifier,'status':'BLOCKED','code':error.code,'reason':str(error)}))
            except Exception:
                db.rollback();raise
    return 1 if failed else 0


if __name__=='__main__':raise SystemExit(main())