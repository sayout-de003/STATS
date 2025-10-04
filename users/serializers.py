# apps/users/serializers.py
from django.contrib.auth import password_validation
from rest_framework import serializers
from .models import (
    User, Profile, Role, KYCSubmission, KYCDocument, DocumentType,
    BusinessProfile, BusinessOwner
)


# --- Business Profile Serializers ---
class BusinessOwnerSerializer(serializers.ModelSerializer):
    """Serializer for business ownership relationships"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = BusinessOwner
        fields = ('id', 'user', 'user_email', 'user_name', 'ownership_type', 'ownership_percentage', 'is_primary_contact', 'created_at')
        read_only_fields = ('id', 'created_at')


class BusinessProfileSerializer(serializers.ModelSerializer):
    """Serializer for business profiles"""
    owners = BusinessOwnerSerializer(many=True, read_only=True)
    is_kyb_verified = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = BusinessProfile
        fields = (
            'id', 'name', 'registration_number', 'tax_id', 'business_type', 'industry',
            'address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country',
            'phone', 'email', 'website', 'is_kyb_verified', 'created_at', 'updated_at', 'owners'
        )
        read_only_fields = ('id', 'is_kyb_verified', 'created_at', 'updated_at')


# --- Document & KYC Serializers ---
class DocumentTypeSerializer(serializers.ModelSerializer):
    """Lists the available document types that can be uploaded."""
    required_roles = serializers.StringRelatedField(many=True, read_only=True)
    
    class Meta:
        model = DocumentType
        fields = (
            'id', 'name', 'applicable_to', 'is_active', 'is_required',
            'required_roles', 'max_file_size_mb', 'allowed_file_types'
        )


class KYCDocumentSerializer(serializers.ModelSerializer):
    """Displays document info within a submission."""
    document_type = DocumentTypeSerializer(read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    
    class Meta:
        model = KYCDocument
        fields = (
            'id', 'document_type', 'file', 'status', 'uploaded_at', 'reviewed_at',
            'reviewed_by', 'reviewed_by_name', 'notes', 'rejection_reason',
            'file_size_bytes', 'file_hash'
        )
        read_only_fields = ('id', 'uploaded_at', 'reviewed_at', 'file_size_bytes', 'file_hash')


class KYCSubmissionSerializer(serializers.ModelSerializer):
    """The main serializer for viewing a KYC Submission and its documents."""
    documents = KYCDocumentSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)
    business_profile = BusinessProfileSerializer(read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    has_all_required_documents = serializers.BooleanField(read_only=True)
    is_kyb_submission = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = KYCSubmission
        fields = (
            'id', 'user', 'business_profile', 'status', 'submitted_at', 'reviewed_at',
            'reviewed_by', 'reviewed_by_name', 'rejection_reason', 'notes',
            'created_at', 'updated_at', 'documents', 'has_all_required_documents',
            'is_kyb_submission'
        )
        read_only_fields = (
            'id', 'submitted_at', 'reviewed_at', 'created_at', 'updated_at',
            'has_all_required_documents', 'is_kyb_submission'
        )


class KYCDocumentUploadSerializer(serializers.ModelSerializer):
    """Used specifically for the document upload action."""
    # We accept the ID of the document type for uploads.
    document_type_id = serializers.IntegerField()
    
    class Meta:
        model = KYCDocument
        fields = ('document_type_id', 'file')
    
    def validate_document_type_id(self, value):
        if not DocumentType.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Invalid or inactive document type ID.")
        return value
    
    def validate_file(self, value):
        """Validate file size and type"""
        if not value:
            raise serializers.ValidationError("No file provided.")
        
        # Get document type for validation
        doc_type_id = self.initial_data.get('document_type_id')
        if doc_type_id:
            try:
                doc_type = DocumentType.objects.get(id=doc_type_id)
                
                # Check file size
                max_size_bytes = doc_type.max_file_size_mb * 1024 * 1024
                if value.size > max_size_bytes:
                    raise serializers.ValidationError(
                        f"File size exceeds maximum allowed size of {doc_type.max_file_size_mb}MB"
                    )
                
                # Check file type
                allowed_types = doc_type.allowed_file_types
                if allowed_types:
                    file_extension = value.name.split('.')[-1].lower()
                    if file_extension not in [ext.lower() for ext in allowed_types]:
                        raise serializers.ValidationError(
                            f"File type '{file_extension}' not allowed. Allowed types: {', '.join(allowed_types)}"
                        )
            except DocumentType.DoesNotExist:
                raise serializers.ValidationError("Invalid document type.")
        
        return value


# NEW: A serializer to represent the Role model.
class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id", "name")


# CHANGED: Updated to include the new address fields from the model.
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = (
            "account_type",
            "avatar", 
            "bio", 
            "phone", 
            "address_line_1", 
            "city", 
            "state", 
            "postal_code", 
            "country"
        )


# CHANGED: This serializer is heavily updated to reflect the new User model structure.
class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    # CHANGED: 'role' is now 'roles' and uses its own serializer for nested representation.
    roles = RoleSerializer(many=True, read_only=True)

    class Meta:
        model = User
        # CHANGED: Updated the fields list.
        fields = (
            "id", 
            "email", 
            "username", 
            "first_name", 
            "last_name", 
            "roles",  # Changed from 'role'
            "company_name", 
            "is_email_verified", # Renamed from 'is_verified'
            "is_kyc_verified",   # New field added
            "profile"
        )


# CHANGED: The registration process now handles assigning roles.
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    # NEW: Accepts a list of Role IDs for assignment during registration.
    roles = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), 
        many=True, 
        required=False # A user can be created without specifying a role.
    )

    class Meta:
        model = User
        # CHANGED: Updated the fields list.
        fields = ("email", "username", "password", "password2", "roles", "company_name")

    def validate_password(self, value):
        password_validation.validate_password(value, self.instance)
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        password = validated_data.pop("password")
        # CHANGED: Pop the roles data before creating the user.
        roles_data = validated_data.pop("roles", None)

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        # CHANGED: Assign roles after the user is saved.
        if roles_data:
            user.roles.set(roles_data)
        else:
            # If no role is provided, assign a default 'Buyer' role.
            # This prevents users from being created with no role.
            buyer_role, created = Role.objects.get_or_create(name="Buyer")
            user.roles.add(buyer_role)

        Profile.objects.create(user=user)
        return user


# No changes needed for the serializers below this line.
# They do not directly interact with the modified models.

class EmailVerificationRequestSerializer(serializers.Serializer):
    pass

class EmailVerificationConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_password(self, value):
        password_validation.validate_password(value, self.instance)
        return value


# CHANGED: Updated to reflect the new Profile model fields.
class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = (
            "account_type",
            "avatar", 
            "bio", 
            "phone",
            "address_line_1",
            "city",
            "state",
            "postal_code",
            "country"
        )


class UserUpdateSerializer(serializers.ModelSerializer):
    profile = ProfileUpdateSerializer(required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "company_name", "profile")

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        
        # Update User instance
        instance = super().update(instance, validated_data)

        # Update Profile instance
        if profile_data:
            profile_serializer = ProfileUpdateSerializer(instance.profile, data=profile_data, partial=True)
            if profile_serializer.is_valid(raise_exception=True):
                profile_serializer.save()
                
        return instance