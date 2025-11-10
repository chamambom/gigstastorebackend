from enum import Enum


# New Enum Definitions
class BookingStatus(str, Enum):
    PENDING = "pending"  # Waiting for provider response (initial state)
    CONFIRMED = "confirmed"  # Both provider and customer have agreed (booking accepted & confirmed)
    CANCELLED = "cancelled"  # Booking cancelled by customer/provider before job starts
    REJECTED = "rejected"  # Provider explicitly rejects
    EXPIRED = "expired"  # Optional: For time-based expiration if no action taken


class JobStatus(str, Enum):
    # Lifecycle of the actual service delivery
    SCHEDULED = "scheduled"  # Job is booked and confirmed, awaiting start
    IN_PROGRESS = "in_progress"  # Optional: Work has started
    COMPLETED_BY_PROVIDER = "completed_by_provider"  # Provider marks job as done
    COMPLETED_BY_CUSTOMER = "completed_by_customer"  # Customer confirms satisfactory completion
    FAILED = "failed"  # Optional: Job could not be completed for some reason


class PaymentStatus(str, Enum):
    # Lifecycle of the payment for the service
    PENDING = "pending"  # Payment is pending (before job complete, or before customer confirms complete)
    DUE = "due"  # Payment is now owed (e.g., after job completed/confirmed)
    PAID = "paid"  # Payment has been processed
    REFUNDED = "refunded"  # Payment was refunded


class CommissionPaymentStatus(str, Enum):  # Inherit from str and Enum
    DUE = "due"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELED = "canceled"
    FAILED = "failed"
    VOIDED = "voided"  # If you want to use this status
    UNCOLLECTIBLE = "uncollectible"  # If you want to use this status
    # Add any other statuses relevant to your commission payment lifecycle

    # Add other statuses as needed


class PaymentMethod(str, Enum):
    HOSTED_INVOICE = "hosted_invoice"  # For payments initiated by provider via Stripe hosted page
    AUTOMATIC = "automatic"  # For Stripe's automatic collection (which we want to avoid for commissions)
    MANUAL_OFFLINE = "manual_offline"  # For payments outside Stripe (e.g., bank transfer, cash)


class PaymentSource(str, Enum):
    STRIPE = "stripe"
    MANUAL_ENTRY = "manual_entry"  # For recording payments manually by admin
    TEST = "test"


class StripeProviderStatus(str, Enum):
    """
    Tracks a provider's journey through the onboarding and verification process.

    Flow:
    1. NOT_STARTED → User hasn't begun provider onboarding
    2. ONBOARDING_IN_PROGRESS → Basic profile/provider details being completed
    3. ACTIVATE_SUBSCRIPTION_COMPLETE → Stripe Customer + Subscription created
    4. CONNECT_VERIFICATION_PENDING → Stripe Connect account created, awaiting KYC/bank verification
    5. ACTIVE → Fully verified, can accept bookings and receive payouts
    6. REJECTED → Application rejected by platform or Stripe
    """

    # Initial States
    NOT_STARTED = "not_started"  # User registered but hasn't started provider onboarding

    # Onboarding States
    ONBOARDING_IN_PROGRESS = "onboarding_in_progress"  # Completing profile/business details

    # Billing & Connect States
    ACTIVATE_SUBSCRIPTION_COMPLETE = "stripe_activate_subscription_complete"  # Stripe Customer created, ready for Connect
    CONNECT_VERIFICATION_PENDING = "connect_verification_pending"  # Connect account created, awaiting Stripe
    # verification

    # Final States
    ACTIVE = "active"  # Fully verified, charges_enabled=True, payouts_enabled=True
    REJECTED = "rejected"  # Application rejected by platform or Stripe compliance
