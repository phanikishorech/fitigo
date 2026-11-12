"""Server-only account message transports. Acceptance is not inbox delivery."""
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from app.core.config import settings


def unavailable(configured=False):
    code = 'ACCOUNT_DELIVERY_FAILED' if configured else 'ACCOUNT_DELIVERY_UNAVAILABLE'
    message = ('The provider did not confirm message acceptance. Try again later or contact your administrator.'
               if configured else 'Account message delivery is not configured. Contact your FitiGo administrator.')
    return HTTPException(503, detail={'code': code, 'message': message})


def safe_url(value):
    try:
        url = urlsplit(value)
        return bool(url.hostname and not url.username and not url.password and not url.fragment and not url.query
                    and not any(c.isspace() for c in value) and '\\' not in value
                    and (url.scheme == 'https' or (settings.environment == 'development'
                         and url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'})))
    except ValueError:
        return False


def frontend_link(path):
    value = (settings.password_reset_frontend_url if path == '/auth/reset-password'
             and settings.password_reset_frontend_url else settings.public_frontend_url.rstrip('/') + path)
    if not safe_url(value):
        raise unavailable()
    return value


def email_ready():
    return bool(settings.email_provider == 'smtp' and settings.smtp_host and settings.smtp_from
                and '\n' not in settings.smtp_from and '\r' not in settings.smtp_from
                and settings.smtp_security in {'starttls', 'ssl'}
                and (not settings.smtp_username or settings.smtp_password.get_secret_value()))


def send_email(address, subject, body):
    if not email_ready():
        raise unavailable()
    try:
        message = EmailMessage()
        message['Subject'], message['From'], message['To'] = subject, settings.smtp_from, address
        message.set_content(body)
        context = ssl.create_default_context()
        cls = smtplib.SMTP_SSL if settings.smtp_security == 'ssl' else smtplib.SMTP
        kwargs = {'context': context} if settings.smtp_security == 'ssl' else {}
        with cls(settings.smtp_host, settings.smtp_port, timeout=10, **kwargs) as smtp:
            if settings.smtp_security == 'starttls':
                smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            if smtp.send_message(message):
                raise unavailable(True)
    except Exception:
        # Never include provider diagnostics, addresses, message bodies or tokens.
        raise unavailable(True) from None


def sms_ready():
    return bool(settings.sms_provider == 'twilio' and re.fullmatch(r'AC[0-9a-fA-F]{32}', settings.twilio_account_sid)
                and settings.twilio_auth_token.get_secret_value()
                and re.fullmatch(r'\+[1-9][0-9]{7,14}', settings.twilio_from_number))


def send_sms(number, body):
    if not sms_ready():
        raise unavailable()
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                f'https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json',
                auth=(settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value()),
                data={'From': settings.twilio_from_number, 'To': number, 'Body': body})
        data = response.json()
        if response.status_code != 201 or not data.get('sid') or data.get('status') not in {'accepted', 'queued', 'sending', 'sent', 'delivered'}:
            raise unavailable(True)
    except Exception:
        raise unavailable(True) from None