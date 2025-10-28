"""
Email template renderer using Jinja2 for easy maintenance
pip install jinja2
"""
from pathlib import Path
from typing import Optional, Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
from src.config.settings import settings


class EmailRenderer:
    """Renders email templates using Jinja2"""

    def __init__(self, template_dir: str = "../templates/emails"):
        """
        Initialize email renderer

        Args:
            template_dir: Directory containing email template files
        """
        # 1. Anchor the path resolution to the file containing this class.
        #    This finds the absolute path of the directory holding email_renderer.py
        anchor_dir = Path(__file__).resolve().parent

        # 2. Determine the path to the project root (The directory containing 'src').
        #    This loop walks up the tree until it finds the folder named 'src'.
        project_root = anchor_dir
        while project_root.name != 'src' and project_root.parent != project_root:
            project_root = project_root.parent

        # 3. If 'src' was found, use its parent as the true root to resolve the full path.
        if project_root.name == 'src':
            self.template_dir = project_root.parent / template_dir
        else:
            # Fallback if the standard structure is not found (CWD-dependent, like your original code)
            self.template_dir = Path(template_dir)

            # Ensure directory exists (harmless with exist_ok=True, and now uses the correct path)
        self.template_dir.mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),  # Jinja2 gets the ABSOLUTE path
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Brand configuration - change once, applies everywhere
        self.brand_config = {
            'logo_url': 'https://gigstastore/images/preview.png',
            'frontend_url': 'https://gigstastore.co.nz',
            'colors': {
                'purple': '#6B21A8',
                'orange': '#FB923C',
                'light_gray': '#F9FAFB',
                'dark_text': '#1F2937',
                'light_text': '#6B7280',
            },
            'company_name': 'Gigsta',
            'support_email': 'support@gigstastore.co.nz',
            'year': datetime.utcnow().year
        }

    def render(self, template_name: str, **context) -> str:
        """
        Render an email template with context

        Args:
            template_name: Name of template file (e.g., 'verify_email.html')
            **context: Variables to pass to template

        Returns:
            Rendered HTML string
        """
        template = self.env.get_template(template_name)

        # Merge brand config with user context
        full_context = {**self.brand_config, **context}

        return template.render(**full_context)

    def verification_email(self, user_email: str, user_name: Optional[str],
                           token: str, frontend_url: str) -> str:
        """Render verification email"""
        return self.render(
            'verify_email.html',
            user_name=user_name or 'there',
            user_email=user_email,
            verify_link=f"{frontend_url}/verify-email?token={token}"
        )

    def password_reset_email(self, user_email: str, user_name: Optional[str],
                             token: str, frontend_url: str) -> str:
        """Render password reset email"""
        return self.render(
            'password_reset.html',
            user_name=user_name or 'there',
            user_email=user_email,
            reset_link=f"{frontend_url}/reset-password?token={token}"
        )

    def password_reset_confirmation_email(self, user_email: str,
                                          user_name: Optional[str],
                                          frontend_url: str) -> str:
        """Render password reset confirmation email"""
        return self.render(
            'password_reset_confirmation.html',
            user_name=user_name or 'there',
            user_email=user_email,
            login_link=f"{frontend_url}/login",
            reset_time=datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')
        )

    def welcome_onboarding_complete_email(self, user_email: str,
                                          user_name: Optional[str],
                                          subscription_id: str,
                                          frontend_url: str) -> str:
        """Render welcome email after billing setup completion"""
        return self.render(
            'welcome_onboarding_complete.html',
            user_name=user_name or 'there',
            user_email=user_email,
            subscription_id=subscription_id,
            dashboard_link=f"{frontend_url}/seeker-dashboard"
        )

    def booking_provider_notification_email(self, provider_email: str,
                                            provider_name: str,
                                            customer_name: str,
                                            customer_email: str,
                                            service_description: str,
                                            service_category: str,
                                            sub_category: str,
                                            booking_id: str,
                                            booking_date: Optional[str] = None,
                                            additional_notes: Optional[str] = None,
                                            frontend_url: str = None) -> str:
        """Render provider booking notification email"""
        return self.render(
            'booking_provider_notification.html',
            provider_name=provider_name,
            customer_name=customer_name,
            customer_email=customer_email,
            service_description=service_description,
            service_category=service_category,
            sub_category=sub_category,
            booking_id=booking_id,
            booking_date=booking_date,
            additional_notes=additional_notes,
            dashboard_link=f"{frontend_url or self.brand_config['frontend_url']}/bookings"
        )

    def booking_customer_confirmation_email(self, customer_email: str,
                                            customer_name: str,
                                            provider_name: str,
                                            service_description: str,
                                            booking_id: str,
                                            booking_date: Optional[str] = None,
                                            frontend_url: str = None) -> str:
        """Render customer booking confirmation email"""
        return self.render(
            'booking_customer_confirmation.html',
            customer_name=customer_name,
            provider_name=provider_name,
            service_description=service_description,
            booking_id=booking_id,
            booking_date=booking_date,
            bookings_link=f"{frontend_url or self.brand_config['frontend_url']}/bookings"
        )

    def welcome_registration_email(self, user_email: str,
                                   user_name: Optional[str],
                                   is_oauth_user: bool = False,
                                   frontend_url: str = None) -> str:
        """Render welcome email after user registration"""
        return self.render(
            'welcome_registration.html',
            user_name=user_name or 'there',
            user_email=user_email,
            is_oauth_user=is_oauth_user,
            dashboard_link=f"{frontend_url or self.brand_config['frontend_url']}/seeker-dashboard"
        )

    def commission_payment_due_email(self, provider_email: str,
                                     provider_name: Optional[str],
                                     booking_id: str,
                                     commission_amount: str,
                                     currency: str,
                                     due_date: str,
                                     payment_link: str,
                                     invoice_id: Optional[str] = None,
                                     frontend_url: str = None) -> str:
        """Render commission payment due notification email"""
        return self.render(
            'commission_payment_due.html',
            provider_name=provider_name or 'Provider',
            booking_id=booking_id,
            commission_amount=commission_amount,
            currency=currency,
            due_date=due_date,
            payment_link=payment_link,
            invoice_id=invoice_id,
            invoices_link=f"{frontend_url or self.brand_config['frontend_url']}/invoice"
        )

    def provider_approved_email(self, provider_email: str,
                                provider_name: Optional[str],
                                frontend_url: str = None) -> str:
        """Render provider approval notification email"""
        return self.render(
            'provider_approved.html',
            provider_name=provider_name or 'there',
            dashboard_link=f"{frontend_url or self.brand_config['frontend_url']}/provider-dashboard"
        )

    def provider_rejected_email(self, provider_email: str,
                                provider_name: Optional[str],
                                rejection_reason: Optional[str] = None,
                                frontend_url: str = None) -> str:
        """Render provider rejection notification email"""
        return self.render(
            'provider_rejected.html',
            provider_name=provider_name or 'there',
            rejection_reason=rejection_reason,
            dashboard_link=f"{frontend_url or self.brand_config['frontend_url']}/provider-dashboard"
        )


# Singleton instance
_renderer = None


def get_email_renderer(template_dir: str = "src/templates/emails") -> EmailRenderer:
    """Get or create email renderer instance"""
    global _renderer
    if _renderer is None:
        _renderer = EmailRenderer(template_dir)
    return _renderer


# Convenience functions for backward compatibility
def get_verification_email(user_email: str, user_name: Optional[str],
                           token: str, frontend_url: str) -> str:
    renderer = get_email_renderer()
    return renderer.verification_email(user_email, user_name, token, frontend_url)


def get_password_reset_email(user_email: str, user_name: Optional[str],
                             token: str, frontend_url: str) -> str:
    renderer = get_email_renderer()
    return renderer.password_reset_email(user_email, user_name, token, frontend_url)


def get_password_reset_confirmation_email(user_email: str, user_name: Optional[str],
                                          frontend_url: str) -> str:
    renderer = get_email_renderer()
    return renderer.password_reset_confirmation_email(user_email, user_name, frontend_url)


def get_welcome_onboarding_complete_email(user_email: str, user_name: Optional[str],
                                          subscription_id: str, frontend_url: str) -> str:
    """Get welcome email after billing setup completion"""
    renderer = get_email_renderer()
    return renderer.welcome_onboarding_complete_email(user_email, user_name, subscription_id, frontend_url)


def get_booking_provider_notification_email(provider_email: str, provider_name: str,
                                            customer_name: str, customer_email: str,
                                            service_description: str, service_category: str,
                                            sub_category: str, booking_id: str,
                                            booking_date: Optional[str] = None,
                                            additional_notes: Optional[str] = None,
                                            frontend_url: str = None) -> str:
    """Get provider booking notification email"""
    renderer = get_email_renderer()
    return renderer.booking_provider_notification_email(
        provider_email, provider_name, customer_name, customer_email,
        service_description, service_category, sub_category, booking_id,
        booking_date, additional_notes, frontend_url
    )


def get_booking_customer_confirmation_email(customer_email: str, customer_name: str,
                                            provider_name: str, service_description: str,
                                            booking_id: str, booking_date: Optional[str] = None,
                                            frontend_url: str = None) -> str:
    """Get customer booking confirmation email"""
    renderer = get_email_renderer()
    return renderer.booking_customer_confirmation_email(
        customer_email, customer_name, provider_name, service_description,
        booking_id, booking_date, frontend_url
    )


def get_welcome_registration_email(user_email: str, user_name: Optional[str],
                                   is_oauth_user: bool = False,
                                   frontend_url: str = None) -> str:
    """Get welcome email after user registration"""  # ← Fixed
    renderer = get_email_renderer()
    return renderer.welcome_registration_email(user_email, user_name, is_oauth_user, frontend_url)


def get_commission_payment_due_email(provider_email: str, provider_name: Optional[str],
                                     booking_id: str, commission_amount: str,
                                     currency: str, due_date: str,
                                     payment_link: str, invoice_id: Optional[str] = None,
                                     frontend_url: str = None) -> str:
    """Get commission payment due notification email"""
    renderer = get_email_renderer()
    return renderer.commission_payment_due_email(
        provider_email, provider_name, booking_id, commission_amount,
        currency, due_date, payment_link, invoice_id, frontend_url
    )


def get_provider_approved_email(provider_email: str, provider_name: Optional[str],
                                frontend_url: str = None) -> str:
    """Get provider approval notification email"""
    renderer = get_email_renderer()
    return renderer.provider_approved_email(provider_email, provider_name, frontend_url)


def get_provider_rejected_email(provider_email: str, provider_name: Optional[str],
                                rejection_reason: Optional[str] = None,
                                frontend_url: str = None) -> str:
    """Get provider rejection notification email"""
    renderer = get_email_renderer()
    return renderer.provider_rejected_email(provider_email, provider_name, rejection_reason, frontend_url)
