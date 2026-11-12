from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select,func
from sqlalchemy.orm import Session,sessionmaker
from app.core.config import settings
from app.models.auth import User
from app.models.notification_delivery import NotificationDelivery,NotificationPreference
from app.services import notification_workflow as workflow
from test_owner_dashboard_mysql import mysql_api,pytestmark


def test_competing_workers_send_once_and_preference_upserts_serialize(mysql_api,monkeypatch):
    monkeypatch.setattr(settings,'notification_workflows_enabled',True)
    monkeypatch.setattr(settings,'notification_email_enabled',True)
    monkeypatch.setattr(workflow.account_delivery,'email_ready',lambda:True)
    sent=[];monkeypatch.setattr(workflow.account_delivery,'send_email',lambda *args:sent.append(1))
    engine=mysql_api[2];factory=sessionmaker(bind=engine)
    with Session(engine) as db:
        db.get(User,3).is_email_verified=True;db.commit()
        workflow.publish(db,3,'PASSWORD_CHANGED',3);db.commit();nid=db.scalar(select(NotificationDelivery.id))
    barrier=Barrier(2)
    def send(_):barrier.wait(timeout=10);return workflow.dispatch(factory,nid)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
    assert len(sent)==1 and all(r in {'ACCEPTED','DISPATCHING'} for r in results), results
    barrier=Barrier(2)
    def update(_):
        with Session(engine) as db:barrier.wait(timeout=10);return workflow.update_preferences(db,3,True)
    with ThreadPoolExecutor(max_workers=2) as pool:assert all(r['operational_email'] for r in pool.map(update,range(2)))
    with Session(engine) as db:assert db.scalar(select(func.count(NotificationPreference.user_id)))==1