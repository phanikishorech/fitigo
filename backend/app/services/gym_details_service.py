"""Shared private submission read model. Callers must authorize access first."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gym import Gym, GymFacility, GymFacilityMapping, GymImage, GymOperatingHours, GymStatusHistory
from app.schemas.gym import GymSubmissionResponse


def get_gym_submission(db: Session, gym_id: int) -> GymSubmissionResponse:
    gym = db.get(Gym, gym_id)
    if gym is None:
        raise HTTPException(status_code=404, detail="Gym not found")
    images = db.scalars(select(GymImage).where(GymImage.gym_id == gym_id)
                        .order_by(GymImage.is_cover.desc(), GymImage.display_order.asc(), GymImage.id.asc())).all()
    facilities = db.scalars(select(GymFacility)
                            .join(GymFacilityMapping, GymFacilityMapping.facility_id == GymFacility.id)
                            .where(GymFacilityMapping.gym_id == gym_id).order_by(GymFacility.name.asc())).all()
    hours = db.scalars(select(GymOperatingHours).where(GymOperatingHours.gym_id == gym_id)
                       .order_by(GymOperatingHours.day_of_week.asc())).all()
    reason = None
    if gym.status == 'REJECTED':
        reason = db.execute(select(GymStatusHistory.reason)
                            .where(GymStatusHistory.gym_id == gym_id, GymStatusHistory.new_status == 'REJECTED')
                            .order_by(GymStatusHistory.created_at.desc(), GymStatusHistory.id.desc()).limit(1)).scalar_one_or_none()
    fields = ('id', 'owner_user_id', 'name', 'description', 'phone', 'email', 'address_line_1',
              'address_line_2', 'city', 'state', 'country', 'postal_code', 'latitude', 'longitude',
              'status', 'is_active', 'has_classes', 'created_at', 'updated_at')
    return GymSubmissionResponse(
        **{name: getattr(gym, name) for name in fields},
        gym_price_per_person=str(gym.gym_price_per_person),
        rejection_reason=reason,
        images=[{name: getattr(image, name) for name in
                 ('id', 'file_path', 'original_filename', 'image_type', 'display_order', 'is_cover', 'created_at')}
                for image in images],
        facilities=[{name: getattr(facility, name) for name in ('id', 'name', 'description', 'icon')}
                    for facility in facilities],
        operating_hours=[{name: getattr(hour, name) for name in ('day_of_week', 'open_time', 'close_time', 'is_closed')}
                         for hour in hours],
    )