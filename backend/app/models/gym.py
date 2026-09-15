from __future__ import annotations

import enum
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class GymStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class Gym(Base):
    __tablename__ = "gyms"
    __table_args__ = (
        Index("ix_gyms_owner_user_id", "owner_user_id"),
        Index("ix_gyms_city", "city"),
        Index("ix_gyms_status", "status"),
        Index("ix_gyms_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(50), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default=GymStatus.DRAFT.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Pricing / features
    # NOTE: Use Numeric for money. SQLAlchemy returns Decimal-like values; we keep type as float for consistency
    # with existing models (e.g. Booking, GymSlot) but treat it as money everywhere.
    gym_price_per_person: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    has_classes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Discovery feature
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    images: Mapped[list["GymImage"]] = relationship("GymImage", back_populates="gym", cascade="all, delete-orphan")
    facility_mappings: Mapped[list["GymFacilityMapping"]] = relationship(
        "GymFacilityMapping", back_populates="gym", cascade="all, delete-orphan"
    )
    operating_hours: Mapped[list["GymOperatingHours"]] = relationship(
        "GymOperatingHours", back_populates="gym", cascade="all, delete-orphan"
    )


class GymImage(Base):
    __tablename__ = "gym_images"
    __table_args__ = (
        Index("ix_gym_images_gym_id", "gym_id"),
        Index("ix_gym_images_is_cover", "is_cover"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    gym: Mapped[Gym] = relationship("Gym", back_populates="images")


class GymFacility(Base):
    __tablename__ = "gym_facilities"
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GymFacilityMapping(Base):
    __tablename__ = "gym_facility_mapping"
    __table_args__ = (
        UniqueConstraint("gym_id", "facility_id"),
        Index("ix_gym_facility_mapping_gym_id", "gym_id"),
        Index("ix_gym_facility_mapping_facility_id", "facility_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gym_facilities.id"), nullable=False)

    gym: Mapped[Gym] = relationship("Gym", back_populates="facility_mappings")
    facility: Mapped[GymFacility] = relationship("GymFacility")


class GymOperatingHours(Base):
    __tablename__ = "gym_operating_hours"
    __table_args__ = (
        UniqueConstraint("gym_id", "day_of_week"),
        Index("ix_gym_operating_hours_gym_id", "gym_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    # 0=Mon ... 6=Sun
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    gym: Mapped[Gym] = relationship("Gym", back_populates="operating_hours")


class GymStatusHistory(Base):
    __tablename__ = "gym_status_history"
    __table_args__ = (
        Index("ix_gym_status_history_gym_id", "gym_id"),
        Index("ix_gym_status_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
