from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.storage.base import StorageService


class LocalStorageService(StorageService):
    def __init__(self) -> None:
        # UPLOAD_DIR can be relative; interpret relative to backend/ directory.
        backend_dir = Path(__file__).resolve().parents[2]
        upload_dir = Path(settings.upload_dir)
        self.base_dir = upload_dir if upload_dir.is_absolute() else (backend_dir / upload_dir)
        # Resolve the configured trusted root (workspace itself may be a junction).
        # Untrusted links below this root are rejected separately.
        self.base_dir = self.base_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_ext(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return ext
        # fallback; actual content-type still validated elsewhere
        return ".bin"

    def save_gym_image(
        self,
        *,
        gym_id: int,
        filename: str,
        content_type: str,
        fileobj: BinaryIO,
    ) -> str:
        # Store under uploads/gyms/gym_<id>/
        rel_dir = Path("gyms") / f"gym_{gym_id}"
        abs_dir = self.base_dir / rel_dir

        ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(content_type)
        if ext is None: raise ValueError('Unsupported image type')
        safe_name = f"{uuid.uuid4().hex}{ext}"
        abs_path = abs_dir / safe_name

        # Never follow a gym directory symlink/junction outside the upload root.
        from app.services.photo_service import PhotoService
        PhotoService.file_path(self, gym_id, str(rel_dir / safe_name).replace('\\', '/'))
        abs_dir.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "xb") as f:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        # Relative path inside uploads
        return str(rel_dir / safe_name).replace("\\", "/")

    def delete(self, *, relative_path: str) -> None:
        rel = Path(relative_path)
        # Prevent path traversal: require it to remain inside base_dir.
        abs_path = (self.base_dir / rel).resolve()
        if not abs_path.is_relative_to(self.base_dir.resolve()) or rel.is_absolute() or '..' in rel.parts:
            raise ValueError("Invalid path")
        current = self.base_dir.absolute()
        for part in [current, *current.parents]:
            if part.is_symlink() or part.is_junction(): raise ValueError('Invalid path')
        for part in rel.parts:
            current = current / part
            if current.is_symlink() or current.is_junction(): raise ValueError('Invalid path')
        if abs_path.exists() and abs_path.is_file():
            os.remove(abs_path)
