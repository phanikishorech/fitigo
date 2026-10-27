"""Disposable review/moderation API regression; scanner proof is required."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models.auth import Role, UserRole
from app.routers import admin
from test_customer_reviews_history import api, booking_api, create, qr, scan, submit


def test_customer_can_review_after_confirmed_booking_and_admin_can_hide(api):
    client, headers, engine = api
    client.app.include_router(admin.router, prefix='/api/v1')
    with Session(engine) as db:
        role = Role(name='ADMIN'); db.add(role); db.flush()
        db.add(UserRole(user_id=5, role_id=role.id)); db.commit()
    booked = create(api, ['Customer'])
    assert submit(api, booked).status_code == 400
    assert scan(api, qr(api, booked)[0]['qr_token'])['success']
    response = submit(api, booked)
    assert response.status_code == 200, response.text
    review_id = response.json()['id']
    assert any(row['id'] == review_id for row in client.get('/api/v1/gyms/1/reviews').json())
    assert client.post(f'/api/v1/admin/reviews/{review_id}/hide', headers=headers[1]).status_code == 403
    assert client.post(f'/api/v1/admin/reviews/{review_id}/hide', headers=headers[5]).status_code == 200
    assert client.get('/api/v1/gyms/1/reviews').json() == []
    assert submit(api, booked, rating=4).json()['status'] == 'HIDDEN'
    assert client.post(f'/api/v1/admin/reviews/{review_id}/publish', headers=headers[5]).status_code == 200
    assert client.get('/api/v1/gyms/1/reviews').json()[0]['rating'] == 4
