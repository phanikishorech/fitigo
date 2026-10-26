"""Central selection and fail-closed configuration; never a fallback provider."""
from urllib.parse import urlparse
from fastapi import HTTPException
from app.core.config import settings
from app.services.razorpay_gateway import configured as razorpay_configured


def validate_configuration(name=None):
    name = name or settings.gateway_name
    if settings.payment_env and "payment_mode" in settings.model_fields_set and settings.payment_mode != settings.gateway_mode:
        raise ValueError("PAYMENT_ENV conflicts with legacy PAYMENT_MODE; remove PAYMENT_MODE or align it")
    if settings.environment == "production" and settings.gateway_mode != "live":
        raise ValueError("Production requires PAYMENT_ENV=production")
    if name == "RAZORPAY":
        if not razorpay_configured():
            raise ValueError("RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET must match the payment environment; live requires RAZORPAY_LIVE_ENABLED=true and ENVIRONMENT=production")
    elif name == "CASHFREE":
        if not settings.cashfree_client_id.strip() or not settings.cashfree_client_secret.get_secret_value().strip():
            raise ValueError("CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET are required")
        if settings.cashfree_api_version != "2026-01-01":
            raise ValueError("Unsupported CASHFREE_API_VERSION; use 2026-01-01")
        url = urlparse(settings.payment_return_url)
        if not url.hostname or url.username or url.password or url.fragment or url.scheme not in {"http", "https"}:
            raise ValueError("PAYMENT_RETURN_URL must be an absolute frontend URL")
        if settings.gateway_mode == "live" and (settings.environment != "production" or url.scheme != "https"):
            raise ValueError("Live Cashfree requires ENVIRONMENT=production and HTTPS PAYMENT_RETURN_URL")
    else:
        raise ValueError("Unsupported PAYMENT_GATEWAY")


def configured():
    if not settings.gateway_required:
        return False
    try:
        validate_configuration()
        return True
    except ValueError:
        return False


def require_gateway(name=None):
    if not settings.gateway_required:
        raise HTTPException(503, detail="Payment gateway is disabled")
    try:
        validate_configuration(name)
    except ValueError as exc:
        raise HTTPException(503, detail=str(exc)) from None


def get_provider(name=None, razorpay_gateway=None):
    name = name or settings.gateway_name
    if name == "RAZORPAY":
        from app.services.razorpay_provider import RazorpayProvider
        return RazorpayProvider(razorpay_gateway)
    if name == "CASHFREE":
        from app.services.cashfree_provider import CashfreeProvider
        return CashfreeProvider()
    raise HTTPException(503, detail="Unsupported payment provider")


def validate_startup():
    if not settings.gateway_required:
        return  # Preserve explicitly disabled legacy development installations.
    validate_configuration()
    if settings.gateway_name == "CASHFREE" and settings.gateway_mode == "live":
        # Cashfree keys have no documented universal environment prefix. Validate
        # against the fixed production API with a read-only request, not a charge.
        try:
            get_provider().probe_credentials()
        except HTTPException:
            raise RuntimeError("Cashfree production credential validation failed; check credentials/environment and connectivity") from None