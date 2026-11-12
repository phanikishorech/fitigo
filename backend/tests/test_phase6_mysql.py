from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.gym import GymImage
from app.models.operations import PhotoDeletion,OperationAudit
from app.services.photo_service import PhotoService
from test_owner_dashboard_mysql import mysql_api,pytestmark
from test_phase6_operations import png


def test_concurrent_photo_deletion_has_one_job_and_one_completion(mysql_api,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'operational_workflows_enabled',True)
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path))
    path=tmp_path/'gyms/gym_1'/('a'*32+'.png');path.parent.mkdir(parents=True);path.write_bytes(png())
    with Session(mysql_api[2]) as db:
        row=GymImage(gym_id=1,file_path='gyms/gym_1/'+'a'*32+'.png',is_cover=True);db.add(row);db.commit();image_id=row.id
    barrier=Barrier(2)
    def remove(_):
        with Session(mysql_api[2]) as db:
            barrier.wait(timeout=10);return PhotoService(db).remove(1,1,image_id)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(remove,range(2)))
    assert results[0]['job_id']==results[1]['job_id'] and all(r['file_deleted'] for r in results)
    assert not path.exists()
    with Session(mysql_api[2]) as db:
        assert db.scalar(select(func.count(PhotoDeletion.id)))==1
        assert db.scalar(select(func.count(OperationAudit.id)))==2


def test_photo_job_listing_works_in_read_only_transaction(mysql_api,monkeypatch):
    from sqlalchemy import text
    from fastapi import Response
    from app.models.auth import User
    from app.routers.owner_members import deletion_jobs
    monkeypatch.setattr(settings,'operational_workflows_enabled',True)
    with mysql_api[2].connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        connection.exec_driver_sql('START TRANSACTION')
        with Session(bind=connection) as db:
            result=deletion_jobs(1,Response(),db,db.get(User,1))
            assert result=={'enabled':True,'items':[]}
        connection.rollback()