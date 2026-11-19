"""Gym-scoped operational directory; never a global customer search."""
from fastapi import HTTPException
from sqlalchemy import select, union, func, or_
from app.core.time import as_ist, utcnow, ist_today
from app.models.auth import User
from app.models.gym import Gym
from app.models.booking import Booking
from app.models.membership import UserMembership, MembershipPause
from app.models.access import Checkin


class OwnerMemberService:
    def __init__(self, db, owner_id, gym_id):
        self.db, self.gym_id = db, gym_id
        if not db.scalar(select(Gym.id).where(Gym.id == gym_id, Gym.owner_user_id == owner_id)):
            raise HTTPException(404, 'Gym not found')

    def scope(self):
        return union(select(Booking.user_id).where(Booking.gym_id == self.gym_id),
            select(UserMembership.user_id).where(UserMembership.gym_id == self.gym_id),
            select(Checkin.user_id).where(Checkin.gym_id == self.gym_id, Checkin.status == 'SUCCESS'))

    def memberships(self, user_id):
        # Multi-Gym plan details/payment at other gyms are deliberately excluded.
        rows = self.db.scalars(select(UserMembership).where(UserMembership.user_id == user_id,
            UserMembership.gym_id == self.gym_id).order_by(UserMembership.id.desc())).all()
        result = []
        for m in rows:
            state = m.status
            if state == 'ACTIVE':
                if m.payment_status != 'PAID': state = 'UNPAID'
                elif as_ist(m.end_at) <= as_ist(utcnow()): state = 'EXPIRED'
                elif as_ist(m.start_at) > as_ist(utcnow()): state = 'UPCOMING'
                elif self.db.scalar(select(MembershipPause.id).where(MembershipPause.membership_id == m.id,
                    MembershipPause.start_date <= ist_today(), MembershipPause.end_date >= ist_today()).limit(1)):
                    state = 'PAUSED'
            result.append({'id': m.id, 'status': state, 'start_at': as_ist(m.start_at), 'end_at': as_ist(m.end_at)})
        return result

    def directory(self, q, limit, offset):
        statement = select(User).where(User.id.in_(self.scope()))
        if q:
            # Literal substring search; no emails/phone numbers exposed/searched.
            statement = statement.where(or_(User.first_name.contains(q, autoescape=True), User.last_name.contains(q, autoescape=True)))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        users = self.db.scalars(statement.order_by(User.id).limit(limit).offset(offset))
        items=[]
        for u in users:
            states=[m['status'] for m in self.memberships(u.id)]
            state=next((s for s in ('ACTIVE','PAUSED','UPCOMING','EXPIRED','CANCELLED','UNPAID') if s in states),'NO_GYM_MEMBERSHIP')
            items.append({'id':u.id,'name':' '.join(n for n in (u.first_name,u.last_name) if n) or f'Member #{u.id}',
                          'membership_status':state})
        return {'items':items,'total':total,'limit':limit,'offset':offset}

    def history(self, user_id, limit, offset):
        user = self.db.scalar(select(User).where(User.id == user_id, User.id.in_(self.scope())))
        if not user: raise HTTPException(404, 'Member not found at this gym')
        bookings=select(Booking).where(Booking.user_id == user_id, Booking.gym_id == self.gym_id)
        visits=select(Checkin).where(Checkin.user_id == user_id, Checkin.gym_id == self.gym_id, Checkin.status == 'SUCCESS')
        from app.services.membership_entitlement import active_memberships, covers
        current_access = covers(active_memberships(self.db, user_id, utcnow()), self.db.get(Gym, self.gym_id))
        return {'id':user.id,'name':' '.join(n for n in (user.first_name,user.last_name) if n) or f'Member #{user.id}',
            'current_membership_access': current_access,
            'memberships':self.memberships(user_id),
            'bookings':[{'id':b.id,'date':b.slot_date,'status':b.status,'attendance_status':b.attendance_status,'quantity':b.quantity}
                for b in self.db.scalars(bookings.order_by(Booking.id.desc()).limit(limit).offset(offset))],
            'visits':[{'id':v.id,'at':as_ist(v.checkin_time),'source':v.access_source,'booking_id':v.booking_id}
                for v in self.db.scalars(visits.order_by(Checkin.checkin_time.desc(),Checkin.id.desc()).limit(limit).offset(offset))],
            'booking_total':self.db.scalar(select(func.count()).select_from(bookings.subquery())),
            'visit_total':self.db.scalar(select(func.count()).select_from(visits.subquery())), 'limit':limit,'offset':offset}