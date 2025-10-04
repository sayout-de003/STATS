from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets, generics, permissions, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    RegisterSerializer, UserSerializer, UserUpdateSerializer,
    KYCDocumentSerializer, EmailVerificationConfirmSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    KYCSubmissionSerializer, KYCDocumentUploadSerializer, DocumentTypeSerializer,
    BusinessProfileSerializer, BusinessOwnerSerializer
)
from .models import (
    User, Profile, Role, KYCSubmission, KYCDocument, DocumentType, 
    EmailVerificationToken, PasswordResetToken, BusinessProfile, BusinessOwner
)
from .tasks import send_verification_email, send_password_reset_email, verify_kyc_submission
from .permissions import IsOwnerOrAdmin

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)


class UserMeView(generics.RetrieveUpdateAPIView):
    """
    Handles GET and PATCH requests for the currently authenticated user.
    GET /api/v1/users/me/   -> retrieve current user
    PATCH /api/v1/users/me/ -> update current user
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return UserUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user


class KYCStatusByIdView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get(self, request, user_id):
        target_user = get_object_or_404(User, id=user_id)
        if not (request.user.is_admin or request.user == target_user):
            return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)
        
        latest = target_user.kyc_submissions.order_by("-submitted_at").first()
        if not latest:
            return Response({"status": "not_submitted"})
        return Response({"status": latest.status, "submitted_at": latest.submitted_at})


# --- KYC/KYB VIEWS (Completely Refactored) ---
class DocumentTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that lists the required KYC/KYB documents.
    It intelligently filters documents based on the user's account type (Individual/Business).
    """
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Use the new is_applicable_for_user method
        return DocumentType.objects.filter(is_active=True).filter(
            id__in=[dt.id for dt in DocumentType.objects.all() if dt.is_applicable_for_user(user)]
        )


class KYCSubmissionViewSet(viewsets.ModelViewSet):
    """
    Manages the end-to-end KYC/KYB submission and verification lifecycle.
    """
    queryset = KYCSubmission.objects.all()
    serializer_class = KYCSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        if self.request.user.is_admin:
            return KYCSubmission.objects.all()
        return KYCSubmission.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if KYCSubmission.objects.filter(user=self.request.user, status__in=[KYCSubmission.STATUS_PENDING, KYCSubmission.STATUS_IN_REVIEW]).exists():
            raise serializers.ValidationError("You already have a pending or in-review submission.")
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="status")
    def status(self, request):
        user = request.user
        latest = KYCSubmission.objects.filter(user=user).order_by("-submitted_at").first()
        if not latest:
            return Response({"status": "not_submitted"})
        return Response({"status": latest.status, "submitted_at": latest.submitted_at})

    @action(detail=True, methods=['post'], url_path='upload-document', serializer_class=KYCDocumentUploadSerializer)
    def upload_document(self, request, pk=None):
        submission = self.get_object()
        if submission.status != KYCSubmission.STATUS_PENDING:
            return Response({'detail': 'This submission is not pending and cannot be modified.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # --- Flexible Validation Logic ---
        doc_type_id = serializer.validated_data['document_type_id']
        doc_type = DocumentType.objects.get(id=doc_type_id)
        account_type = request.user.profile.account_type
        
        is_valid_type = (
            (account_type == Profile.ACCOUNT_TYPE_INDIVIDUAL and doc_type.applicable_to in [DocumentType.APPLICABLE_TO_INDIVIDUAL, DocumentType.APPLICABLE_TO_BOTH]) or
            (account_type == Profile.ACCOUNT_TYPE_BUSINESS and doc_type.applicable_to in [DocumentType.APPLICABLE_TO_BUSINESS, DocumentType.APPLICABLE_TO_BOTH])
        )

        if not is_valid_type:
            return Response({'detail': f"Document type '{doc_type.name}' is not applicable for a '{account_type}' account."}, status=status.HTTP_400_BAD_REQUEST)

        KYCDocument.objects.create(
            submission=submission,
            document_type=doc_type,
            file=serializer.validated_data['file']
        )
        return Response(KYCDocumentSerializer(submission.documents.last()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit-for-review')
    def submit_for_review(self, request, pk=None):
        submission = self.get_object()
        if submission.status != KYCSubmission.STATUS_PENDING:
            return Response({'detail': 'This submission has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Enforce all required documents uploaded before submission
        if not submission.has_all_required_documents():
            missing_docs = []
            required_docs = submission.get_required_documents()
            uploaded_doc_types = set(submission.documents.values_list('document_type_id', flat=True))
            required_doc_types = set(required_docs.values_list('id', flat=True))
            missing_doc_ids = required_doc_types - uploaded_doc_types
            missing_docs = [doc.name for doc in required_docs.filter(id__in=missing_doc_ids)]
            
            return Response({
                'detail': 'Cannot submit for review. Missing required documents.',
                'missing_documents': missing_docs
            }, status=status.HTTP_400_BAD_REQUEST)

        submission.status = KYCSubmission.STATUS_IN_REVIEW
        submission.submitted_at = timezone.now()
        submission.save()
        
        verify_kyc_submission.delay(submission.id)
        return Response(self.get_serializer(submission).data, status=status.HTTP_200_OK)


# --- Business Profile Views for Multi-User KYB ---
class BusinessProfileViewSet(viewsets.ModelViewSet):
    """
    Manages business profiles for KYB (Know Your Business) verification.
    Supports multi-user ownership and management.
    """
    serializer_class = BusinessProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_queryset(self):
        if self.request.user.is_admin:
            return BusinessProfile.objects.all()
        
        # Return businesses where user is an owner
        user_businesses = BusinessOwner.objects.filter(user=self.request.user).values_list('business_id', flat=True)
        return BusinessProfile.objects.filter(id__in=user_businesses)
    
    def perform_create(self, serializer):
        business = serializer.save()
        # Automatically add the creator as the primary owner
        BusinessOwner.objects.create(
            business=business,
            user=self.request.user,
            ownership_type=BusinessOwner.OWNERSHIP_TYPE_OWNER,
            is_primary_contact=True
        )
    
    @action(detail=True, methods=['post'], url_path='add-owner')
    def add_owner(self, request, pk=None):
        """Add a new owner to the business"""
        business = self.get_object()
        
        # Check if user has permission to add owners
        if not (request.user.is_admin or 
                business.owners.filter(user=request.user, is_primary_contact=True).exists()):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        
        user_id = request.data.get('user_id')
        ownership_type = request.data.get('ownership_type', BusinessOwner.OWNERSHIP_TYPE_OWNER)
        ownership_percentage = request.data.get('ownership_percentage')
        is_primary_contact = request.data.get('is_primary_contact', False)
        
        if not user_id:
            return Response({'detail': 'user_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is already an owner
        if business.owners.filter(user=user).exists():
            return Response({'detail': 'User is already an owner of this business.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # If setting as primary contact, unset others
        if is_primary_contact:
            business.owners.update(is_primary_contact=False)
        
        BusinessOwner.objects.create(
            business=business,
            user=user,
            ownership_type=ownership_type,
            ownership_percentage=ownership_percentage,
            is_primary_contact=is_primary_contact
        )
        
        return Response({'detail': 'Owner added successfully.'}, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path='create-kyb-submission')
    def create_kyb_submission(self, request, pk=None):
        """Create a KYB submission for this business"""
        business = self.get_object()
        
        # Check if user has permission to create KYB submission
        if not (request.user.is_admin or 
                business.owners.filter(user=request.user).exists()):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if there's already a pending or in-review submission
        existing_submission = KYCSubmission.objects.filter(
            business_profile=business,
            status__in=[KYCSubmission.STATUS_PENDING, KYCSubmission.STATUS_IN_REVIEW]
        ).first()
        
        if existing_submission:
            return Response({
                'detail': 'A KYB submission is already pending or in review for this business.',
                'submission_id': existing_submission.id
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new KYB submission
        submission = KYCSubmission.objects.create(
            user=request.user,
            business_profile=business,
            status=KYCSubmission.STATUS_PENDING
        )
        
        return Response(KYCSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def request_email_verification(request):
    user = request.user
    if user.is_email_verified:
        return Response({"detail": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)
    token_obj = EmailVerificationToken.objects.create(user=user)
    token = token_obj.generate()
    send_verification_email.delay(user.email, token)
    return Response({"detail": "Verification email queued."})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def confirm_email_verification(request):
    serializer = EmailVerificationConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data["token"]
    try:
        obj = EmailVerificationToken.objects.get(token=token, is_used=False)
        if obj.is_expired():
            return Response({"detail": "Token has expired."}, status=status.HTTP_400_BAD_REQUEST)
        
        user = obj.user
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        obj.is_used = True
        obj.save(update_fields=['is_used'])
        return Response({"detail": "Email verified."})
    except EmailVerificationToken.DoesNotExist:
        return Response({"detail": "Invalid or used token."}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]
    user = User.objects.filter(email=email).first()
    if user:
        token_obj = PasswordResetToken.objects.create(user=user)
        token = token_obj.generate()
        send_password_reset_email.delay(user.email, token)
    return Response({"detail": "If the email exists, a reset link has been sent."})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data["token"]
    new_password = serializer.validated_data["password"]
    try:
        obj = PasswordResetToken.objects.get(token=token, is_used=False)
        if obj.is_expired():
            return Response({"detail": "Token has expired."}, status=status.HTTP_400_BAD_REQUEST)
        
        obj.user.set_password(new_password)
        obj.user.save()
        obj.is_used = True
        obj.save()
        return Response({"detail": "Password changed successfully."})
    except PasswordResetToken.DoesNotExist:
        return Response({"detail": "Invalid or used token."}, status=status.HTTP_400_BAD_REQUEST)