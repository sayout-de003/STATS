# apps/users/models.py
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string
from django.db.models.signals import post_save
from django.dispatch import receiver


# --- AUTH & ROLES ---
# NEW: A dedicated model for roles. This allows you to add/remove roles from the admin panel.
class Role(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="The name of the role, e.g., 'Buyer', 'Seller'")
    description = models.TextField(blank=True, null=True, help_text="A brief description of the role's permissions and purpose.")

    def __str__(self):
        return self.name


class User(AbstractUser):
    # REMOVED: The old 'role' and 'ROLE_CHOICES' fields have been replaced by the ManyToManyField below.
    
    email = models.EmailField(unique=True, help_text="Primary email address, used for login.")
    # CHANGED: Users can now have multiple roles (e.g., be both a buyer and a seller).
    roles = models.ManyToManyField(Role, blank=True, related_name="users")
    company_name = models.CharField(max_length=255, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)  # Renamed for clarity from is_verified
    # NEW: A convenient flag to check KYC status without querying related documents.
    is_kyc_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        # Updated to show multiple roles if they exist.
        role_names = ", ".join([role.name for role in self.roles.all()])
        return f"{self.email} ({role_names or 'No roles'})"
    
    # NEW: Helper properties to make checking roles in your code easier.
    @property
    def is_buyer(self):
        return self.roles.filter(name="Buyer").exists()

    @property
    def is_seller(self):
        return self.roles.filter(name="Seller").exists()

    @property
    def is_operator(self):
        return self.roles.filter(name="Operator").exists()
    
    @property
    def is_admin(self):
        return self.roles.filter(name="Admin").exists() or self.is_staff


class Profile(models.Model):
    ACCOUNT_TYPE_INDIVIDUAL = "individual"
    ACCOUNT_TYPE_BUSINESS = "business"
    ACCOUNT_TYPE_CHOICES = (
        (ACCOUNT_TYPE_INDIVIDUAL, "Individual"),
        (ACCOUNT_TYPE_BUSINESS, "Business"),
    )
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default=ACCOUNT_TYPE_INDIVIDUAL)
    avatar = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    
    # NEW: Added common address fields.
    address_line_1 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Profile: {self.user.email} [{self.get_account_type_display()}]"


# --- KYC/KYB CORE MODELS ---
# NEW: BusinessProfile model for KYB (Know Your Business)
class BusinessProfile(models.Model):
    """
    Company/Business profile for KYB verification.
    Supports multi-user ownership and management.
    """
    name = models.CharField(max_length=255, help_text="Legal business name")
    registration_number = models.CharField(max_length=100, blank=True, null=True, help_text="Company registration number")
    tax_id = models.CharField(max_length=100, blank=True, null=True, help_text="Tax identification number")
    business_type = models.CharField(max_length=100, blank=True, null=True, help_text="Type of business (LLC, Corporation, etc.)")
    industry = models.CharField(max_length=100, blank=True, null=True, help_text="Business industry/sector")
    
    # Address information
    address_line_1 = models.CharField(max_length=255, blank=True, null=True)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    
    # Contact information
    phone = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # KYB status
    is_kyb_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.registration_number or 'No Reg'})"


class BusinessOwner(models.Model):
    """
    Represents ownership relationship between users and business profiles.
    Supports multiple owners per business.
    """
    OWNERSHIP_TYPE_OWNER = "owner"
    OWNERSHIP_TYPE_DIRECTOR = "director"
    OWNERSHIP_TYPE_SHAREHOLDER = "shareholder"
    OWNERSHIP_TYPE_MANAGER = "manager"
    OWNERSHIP_TYPE_CHOICES = (
        (OWNERSHIP_TYPE_OWNER, "Owner"),
        (OWNERSHIP_TYPE_DIRECTOR, "Director"),
        (OWNERSHIP_TYPE_SHAREHOLDER, "Shareholder"),
        (OWNERSHIP_TYPE_MANAGER, "Manager"),
    )
    
    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name="owners")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="business_ownerships")
    ownership_type = models.CharField(max_length=20, choices=OWNERSHIP_TYPE_CHOICES, default=OWNERSHIP_TYPE_OWNER)
    ownership_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Ownership percentage (0-100)")
    is_primary_contact = models.BooleanField(default=False, help_text="Primary contact for this business")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['business', 'user']
        ordering = ['-is_primary_contact', 'ownership_percentage']
    
    def __str__(self):
        return f"{self.user.email} - {self.business.name} ({self.get_ownership_type_display()})"


# NEW: The DocumentType model makes the system flexible.
class DocumentType(models.Model):
    APPLICABLE_TO_INDIVIDUAL = "individual"
    APPLICABLE_TO_BUSINESS = "business"
    APPLICABLE_TO_BOTH = "both"
    APPLICABLE_CHOICES = (
        (APPLICABLE_TO_INDIVIDUAL, "For Individuals Only"),
        (APPLICABLE_TO_BUSINESS, "For Businesses Only"),
        (APPLICABLE_TO_BOTH, "For Both"),
    )
    
    name = models.CharField(max_length=100, unique=True, help_text="e.g., 'Aadhaar Card', 'GST Certificate'")
    applicable_to = models.CharField(max_length=20, choices=APPLICABLE_CHOICES, help_text="Specify who needs to upload this document.")
    is_active = models.BooleanField(default=True, help_text="Admins can deactivate document types to hide them from users.")
    is_required = models.BooleanField(default=True, help_text="Whether this document is required for submission")
    
    # Role-based filtering
    required_roles = models.ManyToManyField(Role, blank=True, help_text="Roles that must upload this document. If empty, applies to all roles.")
    
    # File validation constraints
    max_file_size_mb = models.PositiveIntegerField(default=10, help_text="Maximum file size in MB")
    allowed_file_types = models.JSONField(default=list, help_text="List of allowed file extensions (e.g., ['pdf', 'jpg', 'png'])")
    
    def __str__(self): 
        return f"{self.name} ({self.get_applicable_to_display()})"
    
    def is_applicable_for_user(self, user):
        """
        Check if this document type is applicable for a given user.
        Considers account type, roles, and active status.
        """
        if not self.is_active:
            return False
            
        # Check account type applicability
        account_type = user.profile.account_type
        if account_type == Profile.ACCOUNT_TYPE_BUSINESS:
            if self.applicable_to not in [self.APPLICABLE_TO_BUSINESS, self.APPLICABLE_TO_BOTH]:
                return False
        else:  # Individual
            if self.applicable_to not in [self.APPLICABLE_TO_INDIVIDUAL, self.APPLICABLE_TO_BOTH]:
                return False
        
        # Check role requirements
        if self.required_roles.exists():
            user_roles = user.roles.all()
            if not self.required_roles.filter(id__in=user_roles.values_list('id', flat=True)).exists():
                return False
        
        return True


class KYCSubmission(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IN_REVIEW = "in_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_IN_REVIEW, "In Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kyc_submissions")
    business_profile = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, null=True, blank=True, related_name="kyb_submissions", help_text="For business/company submissions")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    # Reviewer and audit trail
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="kyc_reviewed_submissions")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection, shown to the user.")
    
    # Additional audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True, help_text="Internal notes for reviewers")
    
    class Meta: 
        ordering = ["-submitted_at"]
    
    def __str__(self): 
        return f"KYC Submission for {self.user.email} ({self.status})"
    
    @property
    def is_kyb_submission(self):
        """Check if this is a KYB (business) submission"""
        return self.business_profile is not None
    
    def get_required_documents(self):
        """Get list of required document types for this submission"""
        if self.is_kyb_submission:
            # For business submissions, get business-required documents
            return DocumentType.objects.filter(
                is_active=True,
                is_required=True,
                applicable_to__in=[DocumentType.APPLICABLE_TO_BUSINESS, DocumentType.APPLICABLE_TO_BOTH]
            )
        else:
            # For individual submissions
            return DocumentType.objects.filter(
                is_active=True,
                is_required=True,
                applicable_to__in=[DocumentType.APPLICABLE_TO_INDIVIDUAL, DocumentType.APPLICABLE_TO_BOTH]
            )
    
    def has_all_required_documents(self):
        """Check if all required documents have been uploaded"""
        required_docs = self.get_required_documents()
        uploaded_doc_types = set(self.documents.values_list('document_type_id', flat=True))
        required_doc_types = set(required_docs.values_list('id', flat=True))
        return required_doc_types.issubset(uploaded_doc_types)


class KYCDocument(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    )
    
    submission = models.ForeignKey(KYCSubmission, on_delete=models.CASCADE, related_name="documents")
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="kyc_documents")
    file = models.FileField(upload_to="kyc/%Y/%m/%d/")
    
    # Document status and review
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="kyc_reviewed_documents"
    )
    
    # Notes and feedback
    notes = models.TextField(blank=True, null=True, help_text="Internal notes for reviewers.")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection, shown to the user.")
    
    # File validation metadata
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True, help_text="File size in bytes")
    file_hash = models.CharField(max_length=64, blank=True, null=True, help_text="SHA-256 hash of the file for integrity")
    
    class Meta:
        unique_together = ['submission', 'document_type']
        ordering = ['-uploaded_at']
    
    def __str__(self): 
        return f"Doc [{self.document_type.name}] for Sub. {self.submission.id} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Validate file size and type before saving
        if self.file:
            self._validate_file()
        super().save(*args, **kwargs)
    
    def _validate_file(self):
        """Validate file size and type according to document type constraints"""
        if not self.document_type:
            return
            
        # Check file size
        max_size_bytes = self.document_type.max_file_size_mb * 1024 * 1024
        if self.file.size > max_size_bytes:
            raise ValueError(f"File size exceeds maximum allowed size of {self.document_type.max_file_size_mb}MB")
        
        # Check file type
        allowed_types = self.document_type.allowed_file_types
        if allowed_types:
            file_extension = self.file.name.split('.')[-1].lower()
            if file_extension not in [ext.lower() for ext in allowed_types]:
                raise ValueError(f"File type '{file_extension}' not allowed. Allowed types: {', '.join(allowed_types)}")
        
        # Store file metadata
        self.file_size_bytes = self.file.size
        # Note: file_hash would be calculated here in a real implementation


# --- SIGNALS & TOKENS ---
# NEW: A signal to automatically update the user's is_kyc_verified flag.
@receiver(post_save, sender=KYCSubmission)
def update_user_kyc_status(sender, instance, **kwargs):
    """
    After a KYCSubmission is saved, check if any of the user's documents are approved.
    """
    user = instance.user
    if instance.status == KYCSubmission.STATUS_APPROVED and not user.is_kyc_verified:
        user.is_kyc_verified = True
        user.save(update_fields=['is_kyc_verified'])
    elif instance.status != KYCSubmission.STATUS_APPROVED and user.is_kyc_verified:
        is_still_approved = KYCSubmission.objects.filter(user=user, status=KYCSubmission.STATUS_APPROVED).exists()
        if not is_still_approved:
            user.is_kyc_verified = False
            user.save(update_fields=['is_kyc_verified'])


@receiver(post_save, sender=KYCDocument)
def update_kyc_verification_on_document_change(sender, instance, **kwargs):
    """
    Signal to resync is_kyc_verified when KYCDocument status changes.
    This ensures the user's verification status is always up-to-date.
    """
    submission = instance.submission
    user = submission.user
    
    # Check if all required documents are approved
    required_docs = submission.get_required_documents()
    approved_docs = submission.documents.filter(
        document_type__in=required_docs,
        status=KYCDocument.STATUS_APPROVED
    )
    
    # User is verified if all required documents are approved
    all_required_approved = approved_docs.count() == required_docs.count()
    
    if all_required_approved and not user.is_kyc_verified:
        user.is_kyc_verified = True
        user.save(update_fields=['is_kyc_verified'])
    elif not all_required_approved and user.is_kyc_verified:
        user.is_kyc_verified = False
        user.save(update_fields=['is_kyc_verified'])


# NEW: Abstract base model for tokens to avoid code repetition (DRY principle).
class AbstractToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(help_text="Token expiration time")

    class Meta:
        abstract = True

    def generate(self, expiry_hours=24):
        """Generate a new token with specified expiry time"""
        from django.utils import timezone
        from datetime import timedelta
        
        self.token = get_random_string(64)
        self.expires_at = timezone.now() + timedelta(hours=expiry_hours)
        self.save()
        return self.token

    def is_expired(self):
        """Check if token has expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired()

    def __str__(self):
        return f"Token for {self.user.email} (Used: {self.is_used}, Expired: {self.is_expired()})"

# CHANGED: Now inherits from AbstractToken.
class EmailVerificationToken(AbstractToken):
    # The 'user' field is inherited, but we redefine it to set a custom related_name.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="email_verification_tokens"
    )

# CHANGED: Now inherits from AbstractToken.
class PasswordResetToken(AbstractToken):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="password_reset_tokens"
    )