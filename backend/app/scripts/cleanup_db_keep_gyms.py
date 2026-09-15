"""Dangerous: cleanup DB data while keeping a small set of gyms.

This script is intended for LOCAL/DEV use only.

What it does (default behavior):
  - Keeps gyms with ids in KEEP_GYM_IDS
  - Keeps the owner users of those gyms
  - Keeps ADMIN/SUPER_ADMIN users (so you can still log in)
  - Deletes all bookings/payments/cart/wallet/memberships/reviews/notifications/etc
  - Deletes ALL non-kept gyms and their related rows (images, operating hours, slots, etc.)
  - Clears refresh tokens for all users (forces re-login)

Run:
  python -m app.scripts.cleanup_db_keep_gyms --yes

Dry-run:
  python -m app.scripts.cleanup_db_keep_gyms
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.database.session import SessionLocal
from app.models.auth import RefreshToken, Role, User, UserRole
from app.models.booking import Booking, Payment
from app.models.cart import CartItem
from app.models.class_booking import ClassSession, GymClass, GymSpecialHours
from app.models.gym import Gym, GymFacilityMapping, GymImage, GymOperatingHours, GymStatusHistory
from app.models.membership import GymMembershipPlan, UserMembership
from app.models.notification import NotificationEvent
from app.models.review import GymReview
from app.models.slot import GymSlot, SlotAvailability
from app.models.staff import GymStaffAssignment
from app.models.wallet import WalletAccount, WalletTransaction


KEEP_GYM_IDS = [188, 189, 190, 191, 192, 237]


@dataclass
class DeleteReport:
    label: str
    rows: int


def _is_probably_local_db(url: str) -> bool:
    u = url.lower()
    return "localhost" in u or "127.0.0.1" in u


def _count(db: Session, stmt) -> int:
    return int(db.execute(stmt).scalar_one())


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup DB data and keep only specified gyms")
    parser.add_argument("--yes", action="store_true", help="Actually perform deletes")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass local-db safety check (still requires --yes)",
    )
    args = parser.parse_args()

    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    if settings.environment.lower() != "development" and not args.force:
        raise RuntimeError(
            f"Refusing to run because ENVIRONMENT={settings.environment!r}. Use --force if you really mean it."
        )

    if not _is_probably_local_db(settings.database_url) and not args.force:
        raise RuntimeError(
            "Refusing to run because DATABASE_URL does not look like localhost/127.0.0.1. "
            "Use --force if you really mean it."
        )

    print("====================")
    print("DB cleanup (DANGEROUS)")
    print("ENVIRONMENT:", settings.environment)
    print("DATABASE_URL:", settings.database_url)
    print("KEEP_GYM_IDS:", KEEP_GYM_IDS)
    print("MODE:", "EXECUTE" if args.yes else "DRY-RUN")
    print("====================")

    reports: list[DeleteReport] = []

    with SessionLocal() as db:
        # Compute keep user ids
        keep_owner_user_ids = set(
            db.execute(select(Gym.owner_user_id).where(Gym.id.in_(KEEP_GYM_IDS))).scalars().all()
        )

        admin_role_ids = set(
            db.execute(select(Role.id).where(Role.name.in_([ROLE_ADMIN, ROLE_SUPER_ADMIN]))).scalars().all()
        )
        admin_user_ids: set[int] = set()
        if admin_role_ids:
            admin_user_ids = set(
                db.execute(select(UserRole.user_id).where(UserRole.role_id.in_(admin_role_ids))).scalars().all()
            )

        keep_user_ids = keep_owner_user_ids | admin_user_ids
        print("Keeping owner_user_ids:", sorted(keep_owner_user_ids))
        print("Keeping admin_user_ids:", sorted(admin_user_ids))
        print("Keeping total user_ids:", sorted(keep_user_ids))

        # Pre-counts (for visibility)
        total_gyms = db.execute(select(text("count(*)")).select_from(text("gyms"))).scalar_one()
        print(f"Gyms before: {int(total_gyms)}")

        # Deletion helpers
        def do_delete(label: str, stmt) -> None:
            if args.yes:
                res = db.execute(stmt)
                reports.append(DeleteReport(label=label, rows=int(res.rowcount or 0)))
            else:
                # best-effort count for dry-run
                try:
                    # Convert DELETE ... WHERE ... into SELECT count(*) with same WHERE by using textual count on table
                    # Not always trivial; so just mark unknown.
                    reports.append(DeleteReport(label=label, rows=-1))
                except Exception:
                    reports.append(DeleteReport(label=label, rows=-1))

        # Always clear business data
        do_delete("payments (all)", delete(Payment))
        do_delete("bookings (all)", delete(Booking))
        do_delete("cart_items (all)", delete(CartItem))
        do_delete("wallet_transactions (all)", delete(WalletTransaction))
        do_delete("wallet_accounts (all)", delete(WalletAccount))
        do_delete("user_memberships (all)", delete(UserMembership))
        do_delete("gym_membership_plans (all)", delete(GymMembershipPlan))
        do_delete("gym_reviews (all)", delete(GymReview))
        do_delete("notification_events (all)", delete(NotificationEvent))
        do_delete("gym_staff_assignments (all)", delete(GymStaffAssignment))

        # Classes
        do_delete("class_sessions (all)", delete(ClassSession))
        do_delete("gym_classes (all)", delete(GymClass))
        do_delete("gym_special_hours (all)", delete(GymSpecialHours))

        # Slots/availability: remove everything for non-kept gyms
        non_kept_slot_ids = [
            int(x)
            for x in db.execute(select(GymSlot.id).where(~GymSlot.gym_id.in_(KEEP_GYM_IDS))).scalars().all()
        ]
        if non_kept_slot_ids:
            do_delete(
                "slot_availability (non-kept gyms)",
                delete(SlotAvailability).where(SlotAvailability.gym_slot_id.in_(non_kept_slot_ids)),
            )
        do_delete("gym_slots (non-kept gyms)", delete(GymSlot).where(~GymSlot.gym_id.in_(KEEP_GYM_IDS)))

        # Gym related (non-kept)
        do_delete("gym_operating_hours (non-kept gyms)", delete(GymOperatingHours).where(~GymOperatingHours.gym_id.in_(KEEP_GYM_IDS)))
        do_delete("gym_facility_mapping (non-kept gyms)", delete(GymFacilityMapping).where(~GymFacilityMapping.gym_id.in_(KEEP_GYM_IDS)))
        do_delete("gym_images (non-kept gyms)", delete(GymImage).where(~GymImage.gym_id.in_(KEEP_GYM_IDS)))
        do_delete("gym_status_history (non-kept gyms)", delete(GymStatusHistory).where(~GymStatusHistory.gym_id.in_(KEEP_GYM_IDS)))

        do_delete("gyms (non-kept)", delete(Gym).where(~Gym.id.in_(KEEP_GYM_IDS)))

        # Auth: clear refresh tokens for everybody
        do_delete("refresh_tokens (all)", delete(RefreshToken))

        # Remove role assignments for deleted users; keep for owners/admins
        if keep_user_ids:
            do_delete("user_roles (non-kept users)", delete(UserRole).where(~UserRole.user_id.in_(list(keep_user_ids))))
        else:
            do_delete("user_roles (all)", delete(UserRole))

        # Delete users that are no longer referenced
        if keep_user_ids:
            do_delete("users (non-kept)", delete(User).where(~User.id.in_(list(keep_user_ids))))
        else:
            # if no gyms exist / no keep owners, avoid deleting all users accidentally unless forced
            if not args.force:
                raise RuntimeError("No keep_user_ids were found. Refusing to delete all users unless --force is provided.")
            do_delete("users (all)", delete(User))

        if args.yes:
            db.commit()
        else:
            db.rollback()

        gyms_after = db.execute(select(text("count(*)")).select_from(text("gyms"))).scalar_one()
        print(f"Gyms after ({'would be' if not args.yes else 'now'}): {int(gyms_after)}")

    print("\nDelete summary:")
    for r in reports:
        suffix = "(unknown in dry-run)" if r.rows == -1 else str(r.rows)
        print(f" - {r.label}: {suffix}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
