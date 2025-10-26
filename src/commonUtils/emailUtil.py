# src/utils/emailUtil.py - Keep only the core email sending function

from fastapi_mail import FastMail, MessageSchema
from src.config.settings import settings
import logging

logger = logging.getLogger(__name__)

conf = settings.mail_config


async def send_email(email: str, subject: str, message: str):
    """
    Core email sending utility - used by all services
    """
    print(f"📧 Sending email to {email} | Subject: {subject}")
    try:
        msg = MessageSchema(
            subject=subject,
            recipients=[email],
            body=message,
            subtype="html",
        )
        fm = FastMail(conf)
        await fm.send_message(msg)
        logger.info(f"Email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {str(e)}")
        raise

