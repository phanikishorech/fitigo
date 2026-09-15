from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageService(ABC):
    @abstractmethod
    def save_gym_image(
        self,
        *,
        gym_id: int,
        filename: str,
        content_type: str,
        fileobj: BinaryIO,
    ) -> str:
        """Save an uploaded gym image.

        Returns a **relative** path inside the configured upload dir.
        """

    @abstractmethod
    def delete(self, *, relative_path: str) -> None:
        """Delete a stored file by relative path."""
