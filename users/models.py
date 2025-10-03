# apps/users/models.py
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string
from django.db.models.signals import post_save
from django.dispatch import receiver


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
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
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
        return f"Profile: {self.user.email}"


class KYCDocument(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kyc_documents")
    file = models.FileField(upload_to="kyc/%Y/%m/%d/")
    doc_type = models.CharField(max_length=128, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True, null=True, help_text="Internal notes for reviewers.")
    # NEW: A field to provide feedback to the user upon rejection.
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection, shown to the user.")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="kyc_reviewed"
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"KYC for {self.user.email} [{self.doc_type}] ({self.status})"

# NEW: A signal to automatically update the user's is_kyc_verified flag.
@receiver(post_save, sender=KYCDocument)
def update_user_kyc_status(sender, instance, **kwargs):
    """
    After a KYCDocument is saved, check if any of the user's documents are approved.
    """
    if instance.status == KYCDocument.STATUS_APPROVED:
        instance.user.is_kyc_verified = True
        instance.user.save(update_fields=['is_kyc_verified'])
    else:
        # If a document is rejected or pending, re-check if any OTHER document is still approved.
        is_approved = KYCDocument.objects.filter(user=instance.user, status=KYCDocument.STATUS_APPROVED).exists()
        if not is_approved and instance.user.is_kyc_verified:
            instance.user.is_kyc_verified = False
            instance.user.save(update_fields=['is_kyc_verified'])


# NEW: Abstract base model for tokens to avoid code repetition (DRY principle).
class AbstractToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def generate(self):
        self.token = get_random_string(64)
        self.save()
        return self.token

    def __str__(self):
        return f"Token for {self.user.email} (Used: {self.is_used})"

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