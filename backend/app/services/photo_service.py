"""Durable metadata removal then retryable file cleanup; never delete before commit."""
from datetime import datetime
import hashlib
import re
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.config import settings
from app.models.gym import Gym, GymImage
from app.models.operations import PhotoDeletion
from app.services.operation_audit import record
from app.storage.local import LocalStorageService


class PhotoService:
    def __init__(self, db):
        self.db = db

    def enabled(self):
        if not settings.operational_workflows_enabled:
            raise HTTPException(409, 'Photo deletion is disabled until the operational migration is deployed.')

    def owner(self, owner_id, gym_id):
        gym = self.db.scalar(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_id)
                             .with_for_update().execution_options(populate_existing=True))
        if not gym: raise HTTPException(404, 'Gym not found')
        return gym

    @staticmethod
    def file_path(storage, gym_id, relative):
        # Only files produced by the local uploader are eligible. Legacy/external
        # paths need manual review, never a permissive path fallback.
        if not re.fullmatch(rf'gyms/gym_{gym_id}/[0-9a-f]{{32}}\.(?:png|jpg|jpeg|webp)', relative):
            raise ValueError('UNSAFE_PATH')
        root = storage.base_dir.absolute()
        for part in [root, *root.parents]:
            if part.is_symlink() or part.is_junction(): raise ValueError('UNSAFE_PATH')
        path = root
        for part in Path(relative).parts:
            path = path / part
            if path.is_symlink() or path.is_junction(): raise ValueError('UNSAFE_PATH')
        if not path.resolve().is_relative_to(root.resolve()): raise ValueError('UNSAFE_PATH')
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1): raise ValueError('UNSAFE_PATH')
        return path

    @staticmethod
    def fingerprint(path):
        if not path.exists(): return None
        if path.stat().st_size > 5 * 1024 * 1024: raise ValueError('FILE_TOO_LARGE')
        with path.open('rb') as handle: data=handle.read(5 * 1024 * 1024 + 1)
        if len(data)>5 * 1024 * 1024: raise ValueError('FILE_TOO_LARGE')
        return hashlib.sha256(data).hexdigest()

    def shared_references(self, storage, path, image_id=None):
        # Legacy imports may use backslashes or redundant path components.
        # Compare canonical paths too, not only the new uploader's string form.
        for row in self.db.execute(select(GymImage.id, GymImage.file_path)):
            if row.id == image_id: continue
            try:
                candidate = (storage.base_dir / row.file_path.replace('\\', '/')).resolve()
                if str(candidate).casefold() == str(path.resolve()).casefold(): return True
            except (OSError, ValueError):
                continue
        return False

    @staticmethod
    def present(job):
        return {'job_id': job.id, 'image_id': job.image_id, 'status': job.status,
                'removed_from_gallery': True, 'file_deleted': job.status == 'COMPLETE',
                'error_code': job.error_code}

    def remove(self, owner_id, gym_id, image_id):
        self.enabled()
        self.owner(owner_id, gym_id)
        job = self.db.scalar(select(PhotoDeletion).where(PhotoDeletion.image_id == image_id).with_for_update())
        if job:
            if job.gym_id != gym_id: raise HTTPException(404, 'Image not found')
            self.db.commit()
            return self.process(job.id, owner_id, gym_id)
        image = self.db.scalar(select(GymImage).where(GymImage.id == image_id, GymImage.gym_id == gym_id).with_for_update())
        if not image: raise HTTPException(404, 'Image not found')
        storage = LocalStorageService()
        try:
            path = self.file_path(storage, gym_id, image.file_path)
            fingerprint = self.fingerprint(path)
        except (ValueError, OSError):
            raise HTTPException(409, 'Photo storage path requires manual review; no changes made.') from None
        refs = list(self.db.scalars(select(GymImage.id).where(func.lower(GymImage.file_path) == image.file_path.lower()).with_for_update()))
        if refs != [image.id] or self.shared_references(storage, path, image.id):
            raise HTTPException(409, 'Photo has shared references; no changes made.')
        job = PhotoDeletion(image_id=image.id, gym_id=gym_id, actor_id=owner_id, file_path=image.file_path,
                            storage_root=str(storage.base_dir.resolve()), fingerprint=fingerprint)
        self.db.add(job)
        cover = image.is_cover
        self.db.delete(image)
        self.db.flush()
        remaining = list(self.db.scalars(select(GymImage).where(GymImage.gym_id == gym_id)
            .order_by(GymImage.is_cover.desc(), GymImage.display_order, GymImage.id).with_for_update()))
        if cover or (remaining and not any(i.is_cover for i in remaining)):
            for i, row in enumerate(remaining): row.is_cover = i == 0
        for i, row in enumerate(remaining): row.display_order = i
        record(self.db, 'PHOTO_REMOVAL_REQUESTED', image_id, owner_id, gym_id=gym_id, job_id=job.id)
        self.db.commit()  # A failed commit has not touched the file.
        return self.process(job.id, owner_id, gym_id)

    def process(self, job_id, owner_id=None, gym_id=None):
        self.enabled()
        initial = self.db.get(PhotoDeletion, job_id)
        if not initial or (gym_id is not None and initial.gym_id != gym_id): raise HTTPException(404, 'Cleanup job not found')
        if owner_id is not None: self.owner(owner_id, initial.gym_id)
        else: self.db.scalar(select(Gym).where(Gym.id == initial.gym_id).with_for_update())
        job = self.db.scalar(select(PhotoDeletion).where(PhotoDeletion.id == job_id).with_for_update().execution_options(populate_existing=True))
        if job.status == 'COMPLETE':
            result = self.present(job); self.db.commit(); return result
        job.attempts += 1
        try:
            storage = LocalStorageService()
            if str(storage.base_dir.resolve()) != job.storage_root: raise ValueError('STORAGE_ROOT_CHANGED')
            path = self.file_path(storage, job.gym_id, job.file_path)
            if self.db.scalar(select(GymImage.id).where(func.lower(GymImage.file_path) == job.file_path.lower()).limit(1).with_for_update()):
                raise ValueError('SHARED_REFERENCE')
            if self.shared_references(storage, path): raise ValueError('SHARED_REFERENCE')
            current = self.fingerprint(path)
            if current is not None:
                if current != job.fingerprint: raise ValueError('FILE_CHANGED')
                path.unlink()  # Exact validated path only; never recursive.
            job.status, job.completed_at, job.error_code = 'COMPLETE', datetime.utcnow(), None
            record(self.db, 'PHOTO_FILE_REMOVED', job.image_id, owner_id, reason_code='AUTOMATED_CLEANUP', job_id=job.id)
        except ValueError as error:
            job.status, job.error_code = 'BLOCKED', str(error)
        except OSError:
            job.status, job.error_code = 'PENDING', 'STORAGE_UNAVAILABLE'
        self.db.commit()  # If interrupted after unlink, retry sees missing file and completes.
        return self.present(job)