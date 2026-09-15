from __future__ import annotations

import os

# Allow running this file directly (python app/scripts/seed_dev.py) as well as as a module
# (python -m app.scripts.seed_dev). When run as a file, Python's import root becomes
# backend/app/scripts, which breaks `from app...` imports.
if __name__ == "__main__":
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]  # .../backend
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.core.roles import (
    ALL_ROLES,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_GYM_OWNER,
)
from app.database.session import SessionLocal
from app.models.auth import User
from app.services.auth_service import AuthService
from app.models.gym import GymFacility
from app.models.gym import Gym
from app.models.slot import GymSlot, SlotAvailability
from app.models.membership import GymMembershipPlan

from datetime import datetime, time, timedelta

from pathlib import Path

from app.core.config import settings
from app.models.gym import Gym, GymFacility, GymFacilityMapping, GymImage, GymOperatingHours
from app.models.class_booking import GymClass, ClassSession, ClassSessionStatus
from app.models.membership import MembershipStatus, UserMembership
from app.models.review import GymReview


def seed_dev_users() -> None:
    """Seed development users.

    Creates:
    - admin@example.com  (ADMIN)
    - owner@example.com  (GYM_OWNER)
    - customer@example.com (CUSTOMER)

    Password is controlled via env (or defaults to 'password1234').
    """

    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    environment = os.getenv("ENVIRONMENT", "development")
    if environment != "development":
        raise RuntimeError("Seeding is allowed only in development environment")

    password = os.getenv("DEV_SEED_PASSWORD", "password1234")

    db = SessionLocal()
    try:
        svc = AuthService(db)

        # Ensure roles exist
        for r in sorted(ALL_ROLES):
            svc.repo.get_or_create_role(r)
        db.commit()

        def _ensure_user(email: str, role: str, first: str, last: str) -> None:
            existing = db.execute(select(User).where(User.email == email)).scalars().first()
            if not existing:
                svc.register_user(
                    first_name=first,
                    last_name=last,
                    email=email,
                    phone=None,
                    password=password,
                    role_name=role,
                )
                return

            # Ensure the required role exists on the existing user.
            current_roles = set(svc.repo.get_role_names(existing.id))
            if role not in current_roles:
                role_obj = svc.repo.get_or_create_role(role)
                svc.repo.assign_role(existing.id, role_obj.id)
                db.commit()

        _ensure_user("admin@example.com", ROLE_ADMIN, "Dev", "Admin")
        _ensure_user("owner@example.com", ROLE_GYM_OWNER, "Dev", "Owner")
        _ensure_user("customer@example.com", ROLE_CUSTOMER, "Dev", "Customer")

        # Seed a few facilities (idempotent)
        existing_names = {row[0] for row in db.execute(select(GymFacility.name)).all()}
        facility_seed = [
            ("Cardio", "Treadmills, bikes", "heart"),
            ("Strength", "Weights and machines", "dumbbell"),
            ("Yoga", "Yoga mats / studio", "lotus"),
            ("Shower", "Shower facilities", "shower"),
            ("Parking", "Parking available", "parking"),
        ]
        for name, desc, icon in facility_seed:
            if name not in existing_names:
                db.add(GymFacility(name=name, description=desc, icon=icon))
        db.commit()

        print("Seed complete. Password:", password)
    finally:
        db.close()


def seed_sample_gyms_and_slots() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        # Find owner
        owner = db.execute(select(User).where(User.email == "owner@example.com")).scalars().first()
        if not owner:
            return

        # Sample gyms.
        # Coords are stored as strings in DB schema for now.
        # Keep "city" consistent so customer search works.
        #
        # We include a Kukatpally cluster so Screen 3 (Nearby Gyms) shows
        # meaningful data using the default Kukatpally location.
        samples = [
            # name, city, state, address_1, locality(address_line_2), postal, lat, lon, is_featured
            (
                "FitZone Premium Gym",
                "Hyderabad",
                "Telangana",
                "KPHB Phase 2, Near Forum Sujana Mall",
                "Kukatpally",
                "500072",
                "17.4939",
                "78.4006",
                True,
            ),
            (
                "PowerHouse Strength Club",
                "Hyderabad",
                "Telangana",
                "Vivekananda Nagar Rd, KPHB",
                "Kukatpally",
                "500072",
                "17.4976",
                "78.3922",
                False,
            ),
            (
                "Zen Yoga & Mobility Studio",
                "Hyderabad",
                "Telangana",
                "Pragathi Nagar Main Rd",
                "Kukatpally",
                "500072",
                "17.5019",
                "78.4034",
                False,
            ),
            (
                "Pulse Cardio Gym",
                "Hyderabad",
                "Telangana",
                "Road No 1, Sri Nagar Colony",
                "Kukatpally",
                "500072",
                "17.4897",
                "78.4097",
                False,
            ),
            (
                "IronTemple Fitness",
                "Hyderabad",
                "Telangana",
                "Allwyn Colony, Phase 1",
                "Kukatpally",
                "500072",
                "17.4863",
                "78.3958",
                False,
            ),

            # Bengaluru samples (kept for other dev flows)
            ("FitZone Area A", "Bengaluru", "Karnataka", "MG Road", "Central Bengaluru", "560001", "12.9716", "77.5946", True),
            ("PowerFit Area B", "Bengaluru", "Karnataka", "Indiranagar", "Indiranagar", "560038", "12.9352", "77.6245", False),
            ("Flex Fitness Area C", "Bengaluru", "Karnataka", "HSR Layout", "HSR Layout", "560102", "12.9141", "77.6446", False),
        ]

        # Facilities list (existing in DB via seed_dev_users)
        facility_rows = list(db.execute(select(GymFacility)).scalars().all())
        facility_by_name = {f.name: f for f in facility_rows}
        wanted_facilities = [
            facility_by_name.get("Cardio"),
            facility_by_name.get("Strength"),
            facility_by_name.get("Yoga"),
            facility_by_name.get("Shower"),
            facility_by_name.get("Parking"),
        ]
        wanted_facilities = [f for f in wanted_facilities if f is not None]

        # uploads base dir
        backend_dir = Path(__file__).resolve().parents[3]  # .../backend
        upload_dir = Path(settings.upload_dir)
        abs_uploads = upload_dir if upload_dir.is_absolute() else (backend_dir / upload_dir)

        def _write_svg(abs_path: Path, title: str, subtitle: str) -> None:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            safe_title = title.replace("&", "and")
            safe_sub = subtitle.replace("&", "and")
            svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900'>
  <defs>
    <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0' stop-color='#0ea5e9'/>
      <stop offset='0.55' stop-color='#2d6cff'/>
      <stop offset='1' stop-color='#00d2a0'/>
    </linearGradient>
    <filter id='shadow' x='-20%' y='-20%' width='140%' height='140%'>
      <feDropShadow dx='0' dy='18' stdDeviation='26' flood-color='#020617' flood-opacity='0.35'/>
    </filter>
  </defs>
  <rect width='1600' height='900' fill='url(#g)'/>
  <g filter='url(#shadow)'>
    <rect x='120' y='190' rx='36' ry='36' width='1360' height='520' fill='rgba(255,255,255,0.92)'/>
  </g>
  <text x='200' y='360' font-family='ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial' font-size='62' font-weight='800' fill='#0f172a'>{safe_title}</text>
  <text x='200' y='430' font-family='ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial' font-size='28' font-weight='650' fill='#334155'>{safe_sub}</text>
  <g>
    <rect x='200' y='470' rx='14' ry='14' width='210' height='46' fill='rgba(45,108,255,0.14)' stroke='rgba(45,108,255,0.25)'/>
    <text x='230' y='502' font-family='ui-sans-serif, system-ui' font-size='18' font-weight='800' fill='#0b2a7a'>FITIGO • DEMO</text>
  </g>
</svg>"""
            abs_path.write_text(svg, encoding="utf-8")

        for name, city, state, addr1, locality, postal, lat, lon, featured in samples:
            gym = db.execute(select(Gym).where(Gym.owner_user_id == owner.id, Gym.name == name)).scalars().first()
            if not gym:
                gym = Gym(
                    owner_user_id=owner.id,
                    name=name,
                    city=city,
                    state=state,
                    country="India",
                    address_line_1=addr1,
                    address_line_2=locality,
                    postal_code=postal,
                    description=(
                        f"{name} is a Fitigo partner gym in {locality}. "
                        "Enjoy strength, cardio, and studio training with smooth check-ins and member-friendly facilities."
                    ),
                    latitude=lat,
                    longitude=lon,
                    status="APPROVED",
                    is_active=True,
                    is_featured=bool(featured),
                    gym_price_per_person=150.00,
                    has_classes=False,
                )
                db.add(gym)
                db.flush()
            else:
                # keep idempotent but enrich missing fields
                gym.city = city
                if not gym.state:
                    gym.state = state
                if not gym.country:
                    gym.country = "India"
                if not gym.address_line_1:
                    gym.address_line_1 = addr1
                if not gym.address_line_2:
                    gym.address_line_2 = locality
                if not gym.postal_code:
                    gym.postal_code = postal
                if not gym.description:
                    gym.description = (
                        f"{name} is a Fitigo partner gym in {locality}. "
                        "Enjoy strength, cardio, and studio training with smooth check-ins and member-friendly facilities."
                    )
                if not gym.latitude:
                    gym.latitude = lat
                if not gym.longitude:
                    gym.longitude = lon
                if featured and not bool(getattr(gym, "is_featured", False)):
                    gym.is_featured = True

            # Default pricing if missing
            if not getattr(gym, "gym_price_per_person", None):
                gym.gym_price_per_person = 150.00

            # Seed facilities mapping (idempotent)
            has_fac = db.execute(select(GymFacilityMapping.id).where(GymFacilityMapping.gym_id == gym.id).limit(1)).first()
            if not has_fac and wanted_facilities:
                for f in wanted_facilities:
                    db.add(GymFacilityMapping(gym_id=gym.id, facility_id=int(f.id)))

            # Enable classes if gym has Yoga facility (simple heuristic for dev)
            try:
                gym.has_classes = bool(any(f.name == "Yoga" for f in wanted_facilities))
            except Exception:
                pass

            # Seed operating hours (5am-11pm all days) if none
            has_hours = db.execute(select(GymOperatingHours.id).where(GymOperatingHours.gym_id == gym.id).limit(1)).first()
            if not has_hours:
                for dow in range(7):
                    db.add(
                        GymOperatingHours(
                            gym_id=gym.id,
                            day_of_week=dow,
                            open_time=time.fromisoformat("05:00:00"),
                            close_time=time.fromisoformat("23:00:00"),
                            is_closed=False,
                        )
                    )

            # Seed a basic image gallery using generated SVGs stored in uploads/.
            has_images = db.execute(select(GymImage.id).where(GymImage.gym_id == gym.id).limit(1)).first()
            if not has_images:
                rel_dir = Path("gyms") / f"gym_{int(gym.id)}"
                image_defs = [
                    ("cover.svg", True, 0, f"{name}", f"{locality}, {city}"),
                    ("gallery_1.svg", False, 1, f"{name} • Strength Zone", "Premium equipment & machines"),
                    ("gallery_2.svg", False, 2, f"{name} • Cardio Floor", "Treadmills, bikes, HIIT"),
                    ("gallery_3.svg", False, 3, f"{name} • Studio", "Yoga • Mobility • Functional"),
                ]
                for filename, is_cover, order, t1, t2 in image_defs:
                    abs_path = abs_uploads / rel_dir / filename
                    _write_svg(abs_path, t1, t2)
                    db.add(
                        GymImage(
                            gym_id=gym.id,
                            file_path=str((rel_dir / filename).as_posix()),
                            original_filename=filename,
                            image_type="image/svg+xml",
                            display_order=order,
                            is_cover=bool(is_cover),
                        )
                    )

            # Ensure slot availability rows exist for today so the details page can render class cards.
            # (SlotService also does this when calling /slots, but details page reads directly.)
            today = datetime.utcnow().date()
            slot_ids = [
                int(r[0])
                for r in db.execute(select(GymSlot.id).where(GymSlot.gym_id == gym.id, GymSlot.is_active == 1)).all()
            ]
            if slot_ids:
                existing_av = set(
                    int(r[0])
                    for r in db.execute(
                        select(SlotAvailability.gym_slot_id).where(
                            SlotAvailability.gym_slot_id.in_(slot_ids),
                            SlotAvailability.slot_date == today,
                        )
                    ).all()
                )
                for sid in slot_ids:
                    if sid in existing_av:
                        continue
                    db.add(
                        SlotAvailability(
                            gym_slot_id=sid,
                            slot_date=today,
                            capacity_override=None,
                            booked_count=0,
                            blocked_count=0,
                            status="AVAILABLE",
                        )
                    )

            # Seed gym classes + sessions (for new booking flow) if enabled and none exist.
            if bool(getattr(gym, "has_classes", False)):
                has_class = db.execute(select(GymClass.id).where(GymClass.gym_id == gym.id).limit(1)).first()
                if not has_class:
                    yoga = GymClass(gym_id=gym.id, class_name="Yoga", description="Morning Yoga Session", image_path=None, is_active=True)
                    zumba = GymClass(gym_id=gym.id, class_name="Zumba", description="Evening Zumba", image_path=None, is_active=True)
                    db.add(yoga)
                    db.add(zumba)
                    db.flush()

                    # sessions: today + tomorrow
                    for sess_date in [today, today + timedelta(days=1)]:
                        db.add(
                            ClassSession(
                                gym_class_id=yoga.id,
                                session_date=sess_date,
                                start_time=time.fromisoformat("07:00:00"),
                                end_time=time.fromisoformat("08:00:00"),
                                maximum_capacity=15,
                                booked_capacity=7,
                                price_per_person=200.00,
                                status=ClassSessionStatus.AVAILABLE.value,
                            )
                        )
                        db.add(
                            ClassSession(
                                gym_class_id=zumba.id,
                                session_date=sess_date,
                                start_time=time.fromisoformat("18:00:00"),
                                end_time=time.fromisoformat("19:00:00"),
                                maximum_capacity=10,
                                booked_capacity=2,
                                price_per_person=250.00,
                                status=ClassSessionStatus.AVAILABLE.value,
                            )
                        )

            # Seed reviews if none exist for this gym
            has_review = db.execute(select(GymReview.id).where(GymReview.gym_id == gym.id).limit(1)).first()
            if not has_review:
                cust_ids = [
                    int(r[0])
                    for r in db.execute(
                        select(User.id).where(
                            User.email.in_([
                                "customer@example.com",
                                "c2@example.com",
                                "cap_customer@example.com",
                            ])
                        )
                    ).all()
                ]
                if cust_ids:
                    base_comments = [
                        "Great equipment and clean floors.",
                        "Morning crowd is manageable. Trainers are helpful.",
                        "Loved the vibe and the strength section.",
                        "Cardio machines are well maintained.",
                        "Good facilities and easy check-in.",
                    ]
                    ratings = [5, 4, 5, 4, 4]
                    for idx, uid in enumerate(cust_ids[:3]):
                        db.add(
                            GymReview(
                                gym_id=gym.id,
                                user_id=uid,
                                rating=ratings[idx % len(ratings)],
                                comment=base_comments[idx % len(base_comments)],
                                status="PUBLISHED",
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow(),
                            )
                        )

            # Seed membership plans if none
            has_plan = db.execute(select(GymMembershipPlan.id).where(GymMembershipPlan.gym_id == gym.id).limit(1)).first()
            if not has_plan:
                db.add(
                    GymMembershipPlan(
                        gym_id=gym.id,
                        name="Monthly",
                        description="30-day unlimited access",
                        duration_days=30,
                        price="999.00",
                        currency="INR",
                        is_active=True,
                    )
                )
                db.add(
                    GymMembershipPlan(
                        gym_id=gym.id,
                        name="Quarterly",
                        description="90-day unlimited access",
                        duration_days=90,
                        price="2499.00",
                        currency="INR",
                        is_active=True,
                    )
                )

            # Seed slots if none
            has_slots = db.execute(select(GymSlot.id).where(GymSlot.gym_id == gym.id).limit(1)).first()
            if not has_slots:
                slot_seed = [
                    ("5:00 AM - 6:00 AM", "05:00:00", "06:00:00", 20, "100.00"),
                    ("6:00 AM - 7:00 AM", "06:00:00", "07:00:00", 20, "100.00"),
                    ("5:00 PM - 6:00 PM", "17:00:00", "18:00:00", 30, "150.00"),
                    ("6:00 PM - 7:00 PM", "18:00:00", "19:00:00", 30, "150.00"),
                ]
                for nm, st, et, cap, price in slot_seed:
                    db.add(
                        GymSlot(
                            gym_id=gym.id,
                            name=nm,
                            start_time=time.fromisoformat(st),
                            end_time=time.fromisoformat(et),
                            capacity=cap,
                            price=price,
                            is_active=1,
                        )
                    )

        db.commit()

        # Ensure the default dev customer has an active membership for a Kukatpally gym
        customer = db.execute(select(User).where(User.email == "customer@example.com")).scalars().first()
        kukatpally_gym = db.execute(
            select(Gym)
            .where(Gym.owner_user_id == owner.id, Gym.city == "Hyderabad", Gym.address_line_2 == "Kukatpally")
            .order_by(Gym.id.asc())
            .limit(1)
        ).scalars().first()
        if customer and kukatpally_gym:
            plan = db.execute(
                select(GymMembershipPlan)
                .where(GymMembershipPlan.gym_id == kukatpally_gym.id)
                .order_by(GymMembershipPlan.id.asc())
                .limit(1)
            ).scalars().first()

            if plan:
                has_mem = db.execute(
                    select(UserMembership.id).where(
                        UserMembership.user_id == customer.id,
                        UserMembership.gym_id == kukatpally_gym.id,
                        UserMembership.status == MembershipStatus.ACTIVE.value,
                    )
                ).first()
                if not has_mem:
                    now = datetime.utcnow()
                    db.add(
                        UserMembership(
                            user_id=customer.id,
                            gym_id=kukatpally_gym.id,
                            plan_id=plan.id,
                            status=MembershipStatus.ACTIVE.value,
                            start_at=now - timedelta(days=3),
                            end_at=now + timedelta(days=27),
                            cancelled_at=None,
                            paid_amount=plan.price,
                            currency="INR",
                            payment_provider="DUMMY",
                            payment_status="PAID",
                            external_ref="DEV-SEED",
                        )
                    )
                    db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_dev_users()
    seed_sample_gyms_and_slots()
