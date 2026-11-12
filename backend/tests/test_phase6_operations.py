"""Phase 6 real API/service checks, isolated DB and temporary storage only."""
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
import struct
import zlib
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.auth import User, Role, UserRole
from app.models.gym import GymImage
from app.models.operations import OperationAudit, PhotoDeletion
from app.services.operation_audit import record
from app.services.photo_service import PhotoService
from app.services.admin_user_service import AdminUserService
from app.storage.local import LocalStorageService
from test_phase5_workflows import api as phase5_api, booking_api


def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')


@pytest.fixture
def api(phase5_api,monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'operational_workflows_enabled',True)
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path))
    return phase5_api


def photo(api,number=1,cover=True):
    relative=f'gyms/gym_1/{number:032x}.png'
    target=Path(settings.upload_dir)/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(png())
    with Session(api[2]) as db:
        image=GymImage(gym_id=1,file_path=relative,is_cover=cover,display_order=number)
        db.add(image);db.commit();return image.id,target


def test_role_filter_happens_before_pagination_and_multiroles_do_not_duplicate(api):
    with Session(api[2]) as db:
        owner=db.scalar(select(Role.id).where(Role.name=='GYM_OWNER'))
        for uid in range(10,40):
            db.add(User(id=uid,email=f'person{uid}@example.com',first_name='Filtered',password_hash='unused',status='ACTIVE'))
            db.flush()
            if uid%5==0:db.add(UserRole(user_id=uid,role_id=owner))
        db.commit()
        svc=AdminUserService(db)
        assert [u.id for u in svc.list_users(q='Filtered',role='GYM_OWNER',limit=2,offset=2)]==[25,20]
        assert svc.list_users(q='Filtered',role='GYM_OWNER',limit=2,offset=6)==[]


def test_admin_status_audit_is_transactional_idempotent_and_safe(api):
    client,headers,engine=api
    body={'status':'INACTIVE','reason_code':'SECURITY','reason':'password=secret-not-for-audit'}
    assert client.post('/api/v1/admin/users/1/status',headers=headers[2],json=body).status_code==403
    assert client.post('/api/v1/admin/users/1/status',headers=headers[4],json=body).status_code==200
    assert client.post('/api/v1/admin/users/1/status',headers=headers[4],json=body).status_code==200
    with Session(engine) as db:
        rows=db.scalars(select(OperationAudit).where(OperationAudit.action=='USER_STATUS_CHANGED')).all()
        assert len(rows)==1 and rows[0].actor_id==4 and rows[0].reason_code=='SECURITY'
        assert rows[0].context=={'from_status':'ACTIVE','to_status':'INACTIVE'}
        with pytest.raises(ValueError):record(db,'PROFILE_UPDATED',1,1,password='secret')
    audit=client.get('/api/v1/admin/audit-logs',headers=headers[4])
    assert audit.status_code==200 and 'secret-not-for-audit' not in audit.text
    assert audit.json()['items'][0]['action']=='USER_STATUS_CHANGED'
    with Session(engine) as db:
        with patch.object(db,'commit',side_effect=RuntimeError('fixture commit failure')):
            with pytest.raises(RuntimeError):AdminUserService(db).update_status(user_id=1,new_status='ACTIVE',actor_id=4)
        db.rollback()
        assert db.get(User,1).status=='INACTIVE'
        assert db.scalar(select(func.count(OperationAudit.id)))==1


def test_photo_delete_reassigns_cover_and_retries_are_idempotent(api):
    image,path=photo(api);other,otherpath=photo(api,2,False)
    url=f'/api/v1/gym-owner/gyms/1/images/{image}'
    assert api[0].delete(url,headers=api[1][5]).status_code==404
    assert path.exists()
    result=api[0].delete(url,headers=api[1][2]);assert result.status_code==200 and result.json()['file_deleted']
    assert not path.exists() and otherpath.exists()
    assert api[0].delete(url,headers=api[1][2]).json()['job_id']==result.json()['job_id']
    with Session(api[2]) as db:
        assert db.get(GymImage,image) is None and db.get(GymImage,other).is_cover
        assert db.scalar(select(func.count(PhotoDeletion.id)))==1
        assert db.scalar(select(func.count(OperationAudit.id)))==2


def test_photo_storage_failure_and_changed_file_are_honest_and_recoverable(api):
    image,path=photo(api)
    with patch.object(Path,'unlink',side_effect=PermissionError('fixture lock')):
        result=api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).json()
    assert result['status']=='PENDING' and not result['file_deleted'] and path.exists()
    retry=f"/api/v1/gym-owner/gyms/1/image-deletions/{result['job_id']}/retry"
    path.write_bytes(b'replacement-do-not-delete')
    blocked=api[0].post(retry,headers=api[1][2]).json()
    assert blocked['status']=='BLOCKED' and blocked['error_code']=='FILE_CHANGED' and path.exists()
    path.write_bytes(png())
    assert api[0].post(retry,headers=api[1][2]).json()['file_deleted']


def test_commit_failure_never_deletes_file_and_post_unlink_retry_completes(api):
    image,path=photo(api)
    with Session(api[2]) as db:
        with patch.object(db,'commit',side_effect=RuntimeError('fixture')):
            with pytest.raises(RuntimeError):PhotoService(db).remove(2,1,image)
        db.rollback()
        assert path.exists() and db.get(GymImage,image) is not None
        assert db.scalar(select(func.count(PhotoDeletion.id)))==0
    with patch.object(Path,'unlink',side_effect=PermissionError('fixture')):
        result=api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).json()
    with Session(api[2]) as db:
        with patch.object(db,'commit',side_effect=RuntimeError('after unlink')):
            with pytest.raises(RuntimeError):PhotoService(db).process(result['job_id'])
        db.rollback()
    assert not path.exists()
    with Session(api[2]) as db:assert PhotoService(db).process(result['job_id'])['file_deleted']


@pytest.mark.parametrize('relative',['../outside.png','gyms/gym_2/'+'a'*32+'.png','C:/outside.png','gyms/gym_1/not-generated.png'])
def test_unsafe_photo_paths_leave_metadata_and_files_untouched(api,relative):
    with Session(api[2]) as db:
        row=GymImage(gym_id=1,file_path=relative);db.add(row);db.commit();iid=row.id
    assert api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{iid}',headers=api[1][2]).status_code==409
    with Session(api[2]) as db:assert db.get(GymImage,iid) is not None and db.scalar(select(func.count(PhotoDeletion.id)))==0


def test_shared_reference_prevents_delete(api):
    image,path=photo(api)
    with Session(api[2]) as db:
        row=db.get(GymImage,image);db.add(GymImage(gym_id=2,file_path=row.file_path));db.commit()
    assert api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).status_code==409
    assert path.exists()


def test_upload_content_validation_and_extension_are_server_controlled(api):
    client,headers,engine=api;url='/api/v1/gym-owner/gyms/1/images'
    for payload in [b'<script>bad</script>',png()[:-3],png()+b'html']:
        assert client.post(url,headers=headers[2],files={'file':('fake.png',payload,'image/png')}).status_code==400
    assert not list(Path(settings.upload_dir).rglob('*.png'))
    result=client.post(url,headers=headers[2],files={'file':('wrong.html',png(),'image/png')})
    assert result.status_code==200 and result.json()['file_path'].endswith('.png')
    assert (Path(settings.upload_dir)/result.json()['file_path']).read_bytes()==png()
    with Session(engine) as db:assert db.scalar(select(OperationAudit.action))=='PHOTO_ADDED'


def test_storage_delete_cannot_use_sibling_prefix(api,tmp_path):
    sibling=tmp_path.parent/(tmp_path.name+'-sibling');sibling.mkdir();target=sibling/'keep.png';target.write_bytes(b'keep')
    with pytest.raises(ValueError):LocalStorageService().delete(relative_path='../'+sibling.name+'/keep.png')
    assert target.read_bytes()==b'keep'


def test_changed_storage_root_blocks_cleanup(api,tmp_path,monkeypatch):
    image,path=photo(api)
    with patch.object(Path,'unlink',side_effect=PermissionError('fixture')):
        result=api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).json()
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path/'another-root'))
    with Session(api[2]) as db:
        blocked=PhotoService(db).process(result['job_id'])
        assert blocked['error_code']=='STORAGE_ROOT_CHANGED' and path.exists()


def test_canonical_shared_path_and_hardlinks_are_rejected(api,tmp_path):
    image,path=photo(api)
    with Session(api[2]) as db:
        db.add(GymImage(gym_id=2,file_path='gyms\\gym_1\\'+path.name));db.commit()
    assert api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).status_code==409
    second,path2=photo(api,2,False)
    other=tmp_path/'hardlink.png';other.hardlink_to(path2)
    assert api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{second}',headers=api[1][2]).status_code==409
    assert other.exists() and path.exists() and path2.exists()


def test_booking_and_profile_audits_preserve_actor_and_omit_sensitive_values(api):
    from test_booking_access_qr import create,NOW
    from datetime import timedelta
    booking=create(api,day=NOW.date()+timedelta(days=2))
    result=api[0].post(f"/api/v1/gym-owner/bookings/{booking['id']}/cancel",headers=api[1][2],json={'reason':'token=do-not-copy'})
    assert result.status_code==200
    with Session(api[2]) as db:
        row=db.scalar(select(OperationAudit).where(OperationAudit.action=='BOOKING_CANCELLED'))
        assert row.actor_id==2 and row.resource_id==booking['id'] and row.context=={'gym_id':1}
        user=db.get(User,2);user.email='owner@example.com';db.commit()
    result=api[0].patch('/api/v1/users/me',headers=api[1][2],json={'first_name':'Private name','last_name':'Private','email':'owner@example.com','phone':None})
    assert result.status_code==200
    with Session(api[2]) as db:
        row=db.scalar(select(OperationAudit).where(OperationAudit.action=='PROFILE_UPDATED'))
        assert row.actor_id==2 and row.context=={'contact_changed':False}


def test_audit_disabled_means_no_table_dependency(api,monkeypatch):
    monkeypatch.setattr(settings,'operational_workflows_enabled',False)
    with Session(api[2]) as db:
        record(db,'PROFILE_UPDATED',1,1);db.commit()
        assert db.scalar(select(func.count(OperationAudit.id)))==0
    result=api[0].get('/api/v1/gym-owner/gyms/1/image-deletions',headers=api[1][2])
    assert result.json()=={'enabled':False,'items':[]}


def test_missing_file_finishes_cleanup_without_touching_another_photo(api):
    image,path=photo(api);other,otherpath=photo(api,2,False)
    path.unlink()  # explicit temporary test fixture only
    response=api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2])
    assert response.status_code==200 and response.json()['file_deleted'] and otherpath.exists()


def test_operational_audit_cannot_be_edited_through_orm(api):
    with Session(api[2]) as db:
        record(db,'PROFILE_UPDATED',1,1);db.commit()
        row=db.scalar(select(OperationAudit));row.reason_code='OTHER'
        with pytest.raises(ValueError,match='append-only'):db.commit()
        db.rollback()
        row=db.scalar(select(OperationAudit));db.delete(row)
        with pytest.raises(ValueError,match='append-only'):db.commit()
        db.rollback()
        assert db.scalar(select(func.count(OperationAudit.id)))==1


def test_foreign_owner_cannot_read_or_retry_cleanup(api):
    image,path=photo(api)
    with patch.object(Path,'unlink',side_effect=PermissionError('fixture')):
        result=api[0].delete(f'/api/v1/gym-owner/gyms/1/images/{image}',headers=api[1][2]).json()
    for actor in [1,3,5]:
        expected=404 if actor==5 else 403
        assert api[0].get('/api/v1/gym-owner/gyms/1/image-deletions',headers=api[1][actor]).status_code==expected
        assert api[0].post(f"/api/v1/gym-owner/gyms/1/image-deletions/{result['job_id']}/retry",headers=api[1][actor]).status_code==expected
    assert path.exists()