from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, LoginView, LogoutView, UserMeView,
    DocumentTypeViewSet, KYCSubmissionViewSet, KYCStatusByIdView,
    BusinessProfileViewSet,
    request_email_verification, confirm_email_verification,
    password_reset_request, password_reset_confirm
)
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()
router.register(r'document-types', DocumentTypeViewSet, basename='document-type')
router.register(r'kyc-submissions', KYCSubmissionViewSet, basename='kyc-submission')
router.register(r'business-profiles', BusinessProfileViewSet, basename='business-profile')

urlpatterns = [
    # Auth and tokens
    path("auth/register/", RegisterView.as_view(), name="auth_register"),
    path("auth/login/", LoginView.as_view(), name="auth_login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth_logout"),

    # User profile view for the authenticated user
    path("users/me/", UserMeView.as_view(), name="user_me"),

    # KYC routes from the router
    path("", include(router.urls)),

    # KYC status by user id (for admin/owner)
    path("users/<int:user_id>/kyc-status/", KYCStatusByIdView.as_view(), name="kyc_status_by_id"),

    # Email verification
    path("users/verify-email/request/", request_email_verification, name="request_email_verification"),
    path("users/verify-email/confirm/", confirm_email_verification, name="confirm_email_verification"),

    # Password reset
    path("auth/password/reset-request/", password_reset_request, name="password_reset_request"),
    path("auth/password/reset-confirm/", password_reset_confirm, name="password_reset_confirm"),
]