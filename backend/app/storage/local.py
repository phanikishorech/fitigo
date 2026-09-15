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
        abs_dir.mkdir(parents=True, exist_ok=True)

        ext = self._safe_ext(filename)
        safe_name = f"{uuid.uuid4().hex}{ext}"
        abs_path = abs_dir / safe_name

        with open(abs_path, "wb") as f:
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
        if not str(abs_path).startswith(str(self.base_dir.resolve())):
            raise ValueError("Invalid path")
        if abs_path.exists() and abs_path.is_file():
            os.remove(abs_path)
