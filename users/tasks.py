# apps/users/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import EmailVerificationToken, PasswordResetToken, KYCSubmission
import time

# Note: ensure FRONTEND_BASE_URL and DEFAULT_FROM_EMAIL set in settings or .env.

@shared_task(ignore_result=True)
def send_verification_email(email: str, token: str):
    verify_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email/{token}"
    subject = "Verify your email"
    body = f"Please verify your email by visiting: {verify_url}"
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)

@shared_task(ignore_result=True)
def send_password_reset_email(email: str, token: str):
    reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password/{token}"
    subject = "Reset your password"
    body = f"Reset your password by visiting: {reset_url}"
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)

@shared_task(ignore_result=True)
def expire_old_tokens(hours=48):
    """
    Mark tokens older than `hours` as used (so they can't be reused).
    Called by Celery beat on a daily schedule by default.
    """
    cutoff = timezone.now() - timedelta(hours=hours)
    ev_qs = EmailVerificationToken.objects.filter(created_at__lt=cutoff, is_used=False)
    pr_qs = PasswordResetToken.objects.filter(created_at__lt=cutoff, is_used=False)
    ev_count = ev_qs.update(is_used=True)
    pr_count = pr_qs.update(is_used=True)
    return {"expired_email_tokens": ev_count, "expired_password_tokens": pr_count}

@shared_task
def verify_kyc_submission(submission_id):
    """
    This task simulates the process of calling a third-party KYC API.
    """
    try:
        submission = KYCSubmission.objects.get(id=submission_id)
    except KYCSubmission.DoesNotExist:
        return f"Submission with ID {submission_id} not found."

    print(f"Starting KYC verification for submission {submission_id}...")

    # --- THIS IS WHERE YOU INTEGRATE WITH A REAL KYC PROVIDER ---
    # Example logic:
    # provider_api = KYCProvider(api_key=settings.KYC_API_KEY)
    # result = provider_api.verify_submission(submission)
    # is_approved = result.is_successful
    # rejection_reason = result.rejection_reason
    # -------------------------------------------------------------
    
    # --- SIMULATION ---
    time.sleep(10) # Simulate network delay
    is_approved = True # Simulate a successful verification
    rejection_reason = None
    # --- END SIMULATION ---

    if is_approved:
        submission.status = KYCSubmission.STATUS_APPROVED
    else:
        submission.status = KYCSubmission.STATUS_REJECTED
        submission.rejection_reason = rejection_reason or "Verification failed. Please check your documents."
        
    submission.save()
    print(f"Verification complete for submission {submission_id}. Status: {submission.status}")
    return f"Processed submission {submission_id}."