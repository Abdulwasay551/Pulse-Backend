from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import ApiToken, Announcement, DemoRequest, EmployeeInvite, Organization, UserProfile


class ApiTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiToken
        fields = ['id', 'label', 'prefix', 'created_at', 'last_used_at', 'revoked_at']
        read_only_fields = fields

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    # A missing profile (pre-existing accounts) reads as HR with no
    # organization/employee — see core.permissions.is_hr_or_legacy for the
    # matching permission-side default.
    role = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'date_joined',
            'role', 'organization', 'employee', 'is_superuser',
        ]
        read_only_fields = ['id', 'username', 'date_joined', 'role', 'organization', 'employee', 'is_superuser']

    def get_role(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.role if profile else 'HR'

    def get_organization(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.organization.name if profile else None

    def get_employee(self, obj):
        profile = getattr(obj, 'profile', None)
        if not profile or not profile.employee_id:
            return None
        return {'id': profile.employee_id, 'name': profile.employee.name}


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})
    # Only used for a normal (non-invite) signup — ignored/overridden when
    # an invite_token is present, since that signup joins an existing
    # organization instead of creating a new one.
    organization_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    invite_token = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'organization_name', 'invite_token']

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('That username is already taken.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with that email already exists.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        try:
            validate_password(attrs['password'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})

        invite_token = attrs.get('invite_token')
        if not invite_token:
            # Public self-signup (a brand-new Organization + HR profile from
            # just organization_name) is disabled for now — every signup
            # must come from an HR/Admin-issued EmployeeInvite. Revert by
            # deleting this guard; create()'s org-creation branch is
            # untouched and still works once an invite_token is required.
            raise serializers.ValidationError({'invite_token': 'Sign-up is currently invite-only.'})

        invite = EmployeeInvite.objects.filter(token=invite_token, accepted_at__isnull=True).first()
        if invite is None:
            raise serializers.ValidationError({'invite_token': 'This invite link is invalid or already used.'})
        attrs['_invite'] = invite
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        organization_name = validated_data.pop('organization_name', '')
        validated_data.pop('invite_token', None)
        invite = validated_data.pop('_invite', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if invite is not None:
            UserProfile.objects.create(
                user=user, role='Employee', organization=invite.organization, employee=invite.employee
            )
            invite.accepted_at = timezone.now()
            invite.save(update_fields=['accepted_at'])
        else:
            org = Organization.objects.create(
                name=organization_name or f"{user.username}'s organization", created_by=user
            )
            UserProfile.objects.create(user=user, role='HR', organization=org)

        return user


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(label='Username or email')
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        user = authenticate(
            self.context['request'],
            username=attrs['identifier'],
            password=attrs['password'],
        )
        if user is None:
            raise serializers.ValidationError('Incorrect username/email or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')
        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        try:
            validate_password(attrs['new_password'], user=self.context['request'].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        return attrs


class DemoRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemoRequest
        fields = ['full_name', 'email', 'contact_number', 'business_name', 'message']


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['id', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']
