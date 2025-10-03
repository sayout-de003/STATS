from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

# --- New Role Model ---
class Role(models.Model):
    """
    A model to define user roles. This allows for a flexible, many-to-many relationship.
    e.g., A user can be both a "Buyer" and a "Seller".
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

# --- Modified User Model ---
class User(AbstractUser):
    # The old 'role' and 'ROLE_CHOICES' are removed.
    email = models.EmailField(unique=True)
    # A user can now have multiple roles.
    roles = models.ManyToManyField(Role, blank=True, related_name="users")
    company_name = models.CharField(max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        # Display roles in the admin or string representation.
        role_names = ", ".join([role.name for role in self.roles.all()])
        return f"{self.email} ({role_names or 'No roles'})"

# --- Profile Model (No changes needed) ---
class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Profile: {self.user.email}"

# --- Modified KYCDocument Model ---
class KYCDocument(models.Model):
    STATUS_CHOICES = (("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kyc_documents")
    file = models.FileField(upload_to="kyc/%Y/%m/%d/")
    doc_type = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # Added field for providing feedback on rejection.
    rejection_reason = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="kyc_reviewed"
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"KYC {self.user.email} ({self.status})"


from django.utils.crypto import get_random_string

class EmailVerificationToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_tokens")
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def generate_token(self):
        self.token = get_random_string(48)
        self.save()
        return self.token
