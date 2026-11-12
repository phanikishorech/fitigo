"""Bounded outbox worker. Preview by default; --execute can send email.

Run only with approved recipients/provider configuration. UNKNOWN messages never
automatically resend. Do not run against working data during tests.
"""
import argparse
from app.database.session import SessionLocal
from app.services.notification_workflow import due, dispatch


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not 1<=args.limit<=100:parser.error('limit must be 1..100')
    if SessionLocal is None:raise RuntimeError('Database unavailable')
    with SessionLocal() as db:ids=due(db,args.limit)
    print('Eligible jobs:',len(ids),'execute:',args.execute)
    if args.execute:
        for notification_id in ids:print('Notification',notification_id,dispatch(SessionLocal,notification_id))


if __name__=='__main__':main()