"""Invitations grant only the server-stored gym assignment, after explicit acceptance."""
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import ROLE_GYM_OWNER, ROLE_GYM_STAFF
from app.core.security import hash_password, verify_password
from app.models.auth import User
from app.models.gym import Gym
from app.models.staff import GymStaffAssignment, StaffInvitation
from app.repositories.user_repository import UserRepository
from app.services import account_delivery
from app.services.password_service import PasswordService, as_utc, digest, now


class StaffInvitationService:
    def __init__(self, db: Session):
        self.db = db

    def gym(self, owner_id, gym_id, lock=False):
        query = select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_id)
        gym = self.db.scalar(query.with_for_update() if lock else query)
        if not gym:
            raise HTTPException(404, 'Gym not found')
        return gym

    def invite(self, *, owner_user_id, gym_id, email, first_name=None, last_name=None):
        self.gym(owner_user_id, gym_id)
        email = email.strip().lower()
        rate = PasswordService(self.db)
        rate.throttle(f'invite-owner:{owner_user_id}', 20, 3600)
        rate.throttle(f'invite-email:{email}', 5, 3600)
        rate.throttle(f'invite-resend:{gym_id}:{email}', 1, settings.invitation_resend_seconds)
        link = account_delivery.frontend_link('/auth/accept-invitation')
        if not account_delivery.email_ready():
            raise account_delivery.unavailable()
        try:
            user = self.db.scalar(select(User).where(User.email == email).with_for_update())
            if user is None:
                user = User(email=email, first_name=first_name, last_name=last_name,
                            password_hash=hash_password(secrets.token_urlsafe(32)), status='PENDING_INVITATION')
                self.db.add(user); self.db.flush()
            if user.status not in {'ACTIVE', 'PENDING_INVITATION'}:
                raise HTTPException(409, 'This account cannot be invited. Contact your administrator.')
            gym = self.gym(owner_user_id, gym_id, lock=True)
            assignment = self.db.scalar(select(GymStaffAssignment).where(
                GymStaffAssignment.gym_id == gym_id, GymStaffAssignment.user_id == user.id))
            if assignment:
                raise HTTPException(409, 'This account is already assigned to this gym.')
            row = self.db.scalar(select(StaffInvitation).where(
                StaffInvitation.gym_id == gym_id, StaffInvitation.user_id == user.id).with_for_update())
            token = secrets.token_urlsafe(32)
            if row is None:
                row = StaffInvitation(id=str(uuid4()), gym_id=gym_id, user_id=user.id)
                self.db.add(row)
            row.owner_user_id, row.email, row.token_hash = owner_user_id, email, digest(token)
            row.expires_at = now() + timedelta(hours=settings.invitation_expiry_hours)
            row.accepted_at = row.revoked_at = None
            self.db.flush()
            account_delivery.send_email(email, 'Your FitiGo staff invitation',
                f'You have been invited to join {gym.name} as gym staff.\n\n{link}#token={token}\n\n'
                f'This invitation expires in {settings.invitation_expiry_hours} hours and can be accepted once. '
                'New users choose a password. Existing users confirm their current password. '
                'Ignore this message if you do not want to join. No gym access is granted until acceptance.')
            self.db.commit()
            return {'status': 'INVITATION_SENT', 'invitation_id': row.id,
                    'expires_at': as_utc(row.expires_at).isoformat(), 'delivery_status': 'PROVIDER_ACCEPTED'}
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409, 'The invitation changed. Refresh and retry after the resend cooldown.') from None
        except Exception:
            self.db.rollback()
            raise

    def lookup(self, token, lock=False):
        invalid = HTTPException(400, 'This invitation is invalid or expired. Ask the gym owner to resend it.')
        row = self.db.scalar(select(StaffInvitation).where(StaffInvitation.token_hash == digest(token)))
        if not row:
            raise invalid
        uid, gid, owner_id, rid = row.user_id, row.gym_id, row.owner_user_id, row.id
        user_query = select(User).where(User.id == uid)
        user = self.db.scalar(user_query.with_for_update().execution_options(populate_existing=True) if lock else user_query)
        gym_query = select(Gym).where(Gym.id == gid, Gym.owner_user_id == owner_id)
        gym = self.db.scalar(gym_query.with_for_update() if lock else gym_query)
        if lock:
            row = self.db.scalar(select(StaffInvitation).where(StaffInvitation.id == rid).with_for_update().execution_options(populate_existing=True))
        owner = self.db.get(User, owner_id)
        if (not row or row.token_hash != digest(token) or row.accepted_at or row.revoked_at
                or as_utc(row.expires_at) <= now() or not gym or not owner or owner.status != 'ACTIVE'
                or ROLE_GYM_OWNER not in UserRepository(self.db).get_role_names(owner_id)
                or not user or user.status not in {'ACTIVE', 'PENDING_INVITATION'} or user.email.lower() != row.email):
            raise invalid
        return row, user, gym

    def inspect(self, token, client_ip):
        PasswordService(self.db).throttle(f'invite-inspect:{client_ip}', 30, 900)
        row, user, gym = self.lookup(token)
        return {'gym_name': gym.name, 'expires_at': as_utc(row.expires_at).isoformat(),
                'requires_current_password': user.status == 'ACTIVE'}

    def accept(self, token, password, current_password, client_ip):
        rate = PasswordService(self.db)
        rate.throttle(f'invite-accept-ip:{client_ip}', 20, 900)
        rate.throttle(f'invite-accept-token:{digest(token)}', 5, 900)
        try:
            row, user, gym = self.lookup(token, lock=True)
            if user.status == 'PENDING_INVITATION':
                if not password:
                    raise HTTPException(400, 'Choose a password to accept this invitation.')
                PasswordService(self.db)._replace_password(user, password)
                user.status = 'ACTIVE'
            elif not current_password or not verify_password(current_password, user.password_hash):
                raise HTTPException(400, 'Confirm your current account password to accept this invitation.')
            # Password on an existing account is never replaced by an invitation.
            user.is_email_verified = True
            repo = UserRepository(self.db)
            if ROLE_GYM_STAFF not in repo.get_role_names(user.id):
                role = repo.get_or_create_role(ROLE_GYM_STAFF)
                repo.assign_role(user.id, role.id)
            assignment = self.db.scalar(select(GymStaffAssignment).where(
                GymStaffAssignment.gym_id == gym.id, GymStaffAssignment.user_id == user.id))
            if not assignment:
                self.db.add(GymStaffAssignment(gym_id=gym.id, user_id=user.id, role='STAFF'))
                from app.services.operation_audit import record
                record(self.db, 'STAFF_ASSIGNED', gym.id, user.id, user_id=user.id)
            row.accepted_at = now()
            self.db.commit()
            return {'status': 'ACCEPTED', 'message': 'Invitation accepted. Sign in to your staff account.'}
        except Exception:
            self.db.rollback(); raise

    def list(self, owner_id, gym_id):
        self.gym(owner_id, gym_id)
        rows = self.db.scalars(select(StaffInvitation).where(StaffInvitation.gym_id == gym_id,
            StaffInvitation.owner_user_id == owner_id, StaffInvitation.accepted_at.is_(None),
            StaffInvitation.revoked_at.is_(None)).order_by(StaffInvitation.created_at.desc()))
        return [{'id': row.id, 'email': row.email, 'expires_at': as_utc(row.expires_at).isoformat(),
                 'status': 'EXPIRED' if as_utc(row.expires_at) <= now() else 'PENDING'} for row in rows]

    def revoke(self, owner_id, gym_id, invitation_id):
        self.gym(owner_id, gym_id)
        # Same lock order as acceptance, ensuring revoke/accept serialize.
        row = self.db.scalar(select(StaffInvitation).where(StaffInvitation.id == invitation_id,
            StaffInvitation.gym_id == gym_id, StaffInvitation.owner_user_id == owner_id))
        if not row: raise HTTPException(404, 'Invitation not found')
        self.db.scalar(select(User).where(User.id == row.user_id).with_for_update())
        self.gym(owner_id, gym_id, lock=True)
        row = self.db.scalar(select(StaffInvitation).where(StaffInvitation.id == invitation_id).with_for_update().execution_options(populate_existing=True))
        if row.accepted_at: raise HTTPException(409, 'Invitation already accepted. Remove the staff assignment instead.')
        row.revoked_at = now(); self.db.commit()