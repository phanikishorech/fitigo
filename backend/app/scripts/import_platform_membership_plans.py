"""Validate catalog configuration; database writes require explicit --apply and admin ID."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.core.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.models.auth import User
from app.models.platform_membership import PlatformMembershipPlan
from app.repositories.user_repository import UserRepository
from app.schemas.platform_membership import PlatformPlanCreate
from app.services.platform_membership_service import PlatformMembershipService


def read_plans(file: Path) -> list[PlatformPlanCreate]:
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Configuration must contain a non-empty plan list")
    plans = [PlatformPlanCreate.model_validate(item) for item in data]
    if len({plan.code for plan in plans}) != len(plans):
        raise ValueError("Plan codes must be unique")
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--admin-id", type=int)
    parser.add_argument("--apply", action="store_true", help="Write missing plans to the configured database; existing codes are never overwritten")
    args = parser.parse_args()
    plans = read_plans(args.file)
    if not args.apply:
        print(f"Validated {len(plans)} plans. Dry run: no database access or writes.")
        return
    if not args.admin_id:
        parser.error("--apply requires --admin-id for authorization and audit")
    from app.database.session import SessionLocal
    if SessionLocal is None:
        parser.error("Database is not configured")
    with SessionLocal() as db:
        user = db.get(User, args.admin_id)
        roles = set(UserRepository(db).get_role_names(args.admin_id))
        if not user or user.status != "ACTIVE" or not roles.intersection({ROLE_ADMIN, ROLE_SUPER_ADMIN}):
            parser.error("An active ADMIN or SUPER_ADMIN is required")
        created = 0
        for plan in plans:
            if db.scalar(select(PlatformMembershipPlan.id).where(PlatformMembershipPlan.code == plan.code)) is not None:
                continue
            PlatformMembershipService(db).save_plan(plan, actor_id=user.id)
            created += 1
        print(f"Created {created} plans; skipped {len(plans)-created} existing codes. Payments remain disabled.")


if __name__ == "__main__":
    main()