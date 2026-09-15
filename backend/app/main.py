from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.facilities import router as facilities_router
from app.routers.health import router as health_router
from app.routers.gym_owner import router as gym_owner_router
from app.routers.gyms_public import router as gyms_public_router
from app.routers.bookings import router as bookings_router
from app.routers.gym_staff import router as gym_staff_router
from app.routers.memberships import router as memberships_router
from app.routers.users import router as users_router
from app.routers.notifications import router as notifications_router
from app.routers.meta import router as meta_router
from app.routers.profile import router as profile_router
from app.routers.cart import router as cart_router
from app.routers.wallet import router as wallet_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"] ,
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix=settings.api_v1_prefix, tags=["Health"])
    app.include_router(auth_router, prefix=settings.api_v1_prefix, tags=["Auth"])
    app.include_router(users_router, prefix=settings.api_v1_prefix, tags=["Users"])
    app.include_router(admin_router, prefix=settings.api_v1_prefix, tags=["Admin"])
    app.include_router(gym_owner_router, prefix=settings.api_v1_prefix, tags=["Gym Owner"])
    app.include_router(facilities_router, prefix=settings.api_v1_prefix, tags=["Facilities"])
    app.include_router(gyms_public_router, prefix=settings.api_v1_prefix, tags=["Gyms"])
    app.include_router(bookings_router, prefix=settings.api_v1_prefix, tags=["Bookings"])
    app.include_router(gym_staff_router, prefix=settings.api_v1_prefix, tags=["Gym Staff"])
    app.include_router(memberships_router, prefix=settings.api_v1_prefix, tags=["Memberships"])
    app.include_router(notifications_router, prefix=settings.api_v1_prefix, tags=["Notifications"])
    app.include_router(meta_router, prefix=settings.api_v1_prefix, tags=["Meta"])
    app.include_router(profile_router, prefix=settings.api_v1_prefix, tags=["Profile"])
    app.include_router(cart_router, prefix=settings.api_v1_prefix, tags=["Cart"])
    app.include_router(wallet_router, prefix=settings.api_v1_prefix, tags=["Wallet"])

    # Serve local uploads in development.
    backend_dir = Path(__file__).resolve().parents[1]
    upload_dir = Path(settings.upload_dir)
    abs_uploads = upload_dir if upload_dir.is_absolute() else (backend_dir / upload_dir)
    abs_uploads.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(abs_uploads)), name="uploads")
    return app


app = create_app()
