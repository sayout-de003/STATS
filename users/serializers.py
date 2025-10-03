from rest_framework import serializers
from .models import Role, User, Profile, KYCDocument

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['name', 'description']


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['avatar', 'bio']


class UserSerializer(serializers.ModelSerializer):
    # Nest the profile and roles serializers for a richer, readable output
    profile = ProfileSerializer(read_only=True)
    roles = RoleSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'company_name', 'is_verified', 'profile', 'roles'
        ]


class KYCDocumentSerializer(serializers.ModelSerializer):
    # Use ReadOnlyField to display the reviewer's email instead of just their ID
    reviewed_by_email = serializers.ReadOnlyField(source='reviewed_by.email')

    class Meta:
        model = KYCDocument
        fields = [
            'id', 'file', 'doc_type', 'status', 'rejection_reason',
            'uploaded_at', 'reviewed_by_email'
        ]
        # These fields should be set by staff/admins, not the user submitting the form
        read_only_fields = ['status', 'rejection_reason', 'reviewed_by_email']