from typing import List

from pydantic import EmailStr
from pydantic_settings import BaseSettings
from fastapi_mail import ConnectionConfig
import os


class Settings(BaseSettings):
    MONGO_URI: str = os.environ["MONGO_URI"]
    FRONTEND_URL: str = os.environ["FRONTEND_URL"]
    MONGO_DATABASE: str = os.environ["MONGO_DATABASE"]

    ADDRESSABLE_API_KEY: str = os.environ["ADDRESSABLE_API_KEY"]

    PLATFORM_NAME: str = os.environ["PLATFORM_NAME"]

    JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]
    GOOGLE_OAUTH_CLIENT_ID: str = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    GOOGLE_OAUTH_CLIENT_SECRET: str = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    FACEBOOK_APP_ID: str = os.environ["FACEBOOK_APP_ID"]
    FACEBOOK_APP_SECRET: str = os.environ["FACEBOOK_APP_SECRET"]
    CLIENT_ORIGIN: str = os.environ["CLIENT_ORIGIN"]

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    REDIS_URL: str = os.environ["REDIS_URL"]
    RATE_LIMITING_ENABLED: str = os.environ["RATE_LIMITING_ENABLED"]

    # For ALLOWED_IPS, we need special handling
    @property
    def allowed_ips(self) -> List[str]:
        ips = os.getenv("ALLOWED_IPS", "")
        return [ip.strip() for ip in ips.split(",") if ip.strip()]

    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_USERNAME: EmailStr
    MAIL_PASSWORD: str
    MAIL_FROM: EmailStr
    MAIL_STARTTLS: bool
    MAIL_SSL_TLS: bool

    @property
    def mail_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            MAIL_USERNAME=self.MAIL_USERNAME,
            MAIL_PASSWORD=self.MAIL_PASSWORD,
            MAIL_FROM=self.MAIL_FROM,
            MAIL_PORT=self.MAIL_PORT,
            MAIL_SERVER=self.MAIL_SERVER,
            MAIL_STARTTLS=self.MAIL_STARTTLS,
            MAIL_SSL_TLS=self.MAIL_SSL_TLS,
            USE_CREDENTIALS=True
        )

    stripe_keys: dict = {
        "secret_key": os.environ["STRIPE_SECRET_KEY"],
        "publishable_key": os.environ["STRIPE_PUBLISHABLE_KEY"],
        "stripe_price_id_solo_hustle": os.environ["STRIPE_PRICE_ID_SOLO_HUSTLE"],
        # "stripe_price_id_pro_hustle": os.environ["STRIPE_PRICE_ID_PRO_HUSTLE"],
        # "stripe_price_id_elite_hustle": os.environ["STRIPE_PRICE_ID_ELITE_HUSTLE"],
        "webhook_secret": os.environ["STRIPE_WEBHOOK_SIGNING_SECRET"],
        # FIX THIS LINE: Convert to float here
        "commission_rate": float(os.environ["STRIPE_COMMISSION_RATE"]),
        # FIX THIS LINE: Convert to int here for due_days
        "commission_payment_due_days": int(os.environ["STRIPE_COMMISSION_PAYMENT_DUE_DAYS"]),
    }

    R2_ENDPOINT_URL: str = os.environ["R2_ENDPOINT_URL"]
    R2_ACCESS_KEY_ID: str = os.environ["R2_ACCESS_KEY_ID"]
    R2_SECRET_ACCESS_KEY: str = os.environ["R2_SECRET_ACCESS_KEY"]
    R2_BUCKET: str = os.environ["R2_BUCKET"]
    R2_CUSTOM_DOMAIN: str = os.environ["R2_CUSTOM_DOMAIN"]

    class Config:
        env_file = ".env"
        case_sensitive = True


# create a singleton instance
settings = Settings()