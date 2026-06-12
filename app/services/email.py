import smtplib
from email.message import EmailMessage

from ..config import settings


class EmailError(Exception):
    pass


def send_payment_request(to_email: str, subject: str, body: str) -> None:
    if not settings.email_enabled:
        raise EmailError("Email is not configured on this server.")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Could not send email: {e}") from e
