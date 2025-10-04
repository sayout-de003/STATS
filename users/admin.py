from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone

from .models import User, Profile, Role, DocumentType, KYCSubmission, KYCDocument

# --- User Admin ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_display = ("email", "username", "get_roles", "is_staff", "is_kyc_verified", "is_active")
    list_filter = ("roles", "is_staff", "is_email_verified", "is_kyc_verified", "profile__account_type")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "company_name")}),
        ("Roles & Permissions", {"fields": ("roles", "is_active", "is_staff", "is_superuser")}),
        ("Status", {"fields": ("is_email_verified", "is_kyc_verified")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    search_fields = ("email", "first_name", "last_name", "roles__name")
    ordering = ("email",)

    @admin.display(description="Roles")
    def get_roles(self, obj):
        return ", ".join([role.name for role in obj.roles.all()])

# --- KYC Admin ---

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'applicable_to', 'is_active')
    list_filter = ('applicable_to', 'is_active')
    search_fields = ('name',)

class KYCDocumentInline(admin.TabularInline):
    model = KYCDocument
    extra = 0
    readonly_fields = ('uploaded_at', 'image_preview')
    fields = ('document_type', 'file', 'image_preview', 'uploaded_at')

    @admin.display(description="Preview")
    def image_preview(self, obj):
        # Create a small image preview for uploaded images.
        if obj.file and hasattr(obj.file, 'url'):
            # Simple check for image file extensions
            if any(obj.file.url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                return format_html('<img src="{}" style="max-height: 100px; max-width: 150px;" />', obj.file.url)
        return "No preview available"

@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    inlines = [KYCDocumentInline]
    list_display = ('get_user_link', 'get_account_type', 'status', 'document_count', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'user__profile__account_type')
    search_fields = ('user__email', 'user__username')
    ordering = ('-submitted_at',)
    actions = ['approve_submissions', 'reject_submissions']

    def get_fieldsets(self, request, obj=None):
        # Make fields read-only if the submission is no longer pending.
        if obj and obj.status != KYCSubmission.STATUS_PENDING:
            return (
                ('Submission Info (Locked)', {'fields': ('get_user_link', 'status', 'get_account_type')}),
                ('Dates', {'fields': ('submitted_at', 'reviewed_at')}),
                ('Review Details', {'fields': ('reviewed_by', 'rejection_reason')}),
            )
        return (
            ('Submission Details', {'fields': ('user', 'status')}),
            ('Review Notes', {'fields': ('rejection_reason',)}),
        )

    def get_readonly_fields(self, request, obj=None):
        # Always make these fields read-only
        base_fields = ['submitted_at', 'reviewed_at', 'get_user_link', 'get_account_type']
        if obj and obj.status != KYCSubmission.STATUS_PENDING:
            # Add more fields to read-only list if not pending
            return base_fields + ['user', 'status', 'reviewed_by']
        return base_fields

    @admin.display(description="User", ordering='user__email')
    def get_user_link(self, obj):
        # Create a clickable link to the user's admin page.
        link = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', link, obj.user.email)

    @admin.display(description="Account Type", ordering='user__profile__account_type')
    def get_account_type(self, obj):
        return obj.user.profile.get_account_type_display()

    @admin.display(description="# Docs")
    def document_count(self, obj):
        return obj.documents.count()

    # --- NEW: Admin actions for bulk processing ---
    @admin.action(description="Mark selected submissions as Approved")
    def approve_submissions(self, request, queryset):
        updated = queryset.update(
            status=KYCSubmission.STATUS_APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} submission(s) were successfully approved.", messages.SUCCESS)

    @admin.action(description="Mark selected submissions as Rejected")
    def reject_submissions(self, request, queryset):
        # This is a simple rejection. For a real system, you might want a form
        # to enter a rejection reason for all selected items.
        updated = queryset.update(
            status=KYCSubmission.STATUS_REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} submission(s) were rejected.", messages.WARNING)

admin.site.register(Role)

