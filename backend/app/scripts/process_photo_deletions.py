"""Explicit bounded retry worker. No automatic schedule or working-data execution.

Run only in an approved environment after migration, storage review and backup.
"""
import argparse
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models.operations import PhotoDeletion
from app.services.photo_service import PhotoService


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--execute',action='store_true',help='Actually process queued file deletions')
    args=parser.parse_args()
    if not 1 <= args.limit <= 100: parser.error('limit must be 1..100')
    if SessionLocal is None: raise RuntimeError('Database unavailable')
    with SessionLocal() as db:
        PhotoService(db).enabled()
        ids=list(db.scalars(select(PhotoDeletion.id).where(PhotoDeletion.status!='COMPLETE').order_by(PhotoDeletion.id).limit(args.limit)))
    print('Queued jobs:',len(ids),'execute:',args.execute)
    if args.execute:
        for job_id in ids:
            with SessionLocal() as db:
                result=PhotoService(db).process(job_id)
                print('Job',job_id,result['status'],result['error_code'] or '')


if __name__=='__main__': main()