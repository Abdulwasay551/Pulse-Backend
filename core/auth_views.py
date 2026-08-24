from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from integrations.email_provider import send_org_email

from .cookies import clear_auth_cookies, set_auth_cookies
from .serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
)

User = get_user_model()


def _issue_session(response_data, user, request):
    """Builds the JSON body (access token + user) and attaches the refresh
    cookie to the response — the one place both login and register do this,
    so they can't drift apart.
    """
    refresh = RefreshToken.for_user(user)
    response = Response(
        {**response_data, 'access': str(refresh.access_token), 'user': UserSerializer(user).data},
        status=status.HTTP_200_OK,
    )
    set_auth_cookies(response, str(refresh))
    return response


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return _issue_session({'detail': 'Account created.'}, user, request)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return _issue_session({'detail': 'Logged in.'}, user, request)


class RefreshView(APIView):
    """Reads the refresh token from the httpOnly cookie (never the request
    body — the frontend never has the value to send)."""

    permission_classes = [AllowAny]

    def post(self, request):
        token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if not token:
            return Response({'detail': 'No session.'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = TokenRefreshSerializer(data={'refresh': token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            response = Response({'detail': 'Session expired.'}, status=status.HTTP_401_UNAUTHORIZED)
            clear_auth_cookies(response)
            return response

        response = Response({'access': serializer.validated_data['access']})
        new_refresh = serializer.validated_data.get('refresh')
        if new_refresh:
            set_auth_cookies(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass
        response = Response({'detail': 'Logged out.'})
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        # Changing the password invalidates every existing refresh token —
        # otherwise a stolen-but-not-yet-used token would still work after
        # the "compromised" password was changed specifically to stop it.
        for outstanding in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        response = Response({'detail': 'Password changed. Please log in again.'})
        clear_auth_cookies(response)
        return response


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
            # Mirrors owner_scope_id(request)'s own fallback (no profile ==
            # this login is its own tenant) — there's no request/profile
            # object to reuse that helper against here, only the target user.
            profile = getattr(user, 'profile', None)
            owner_id = profile.data_owner_id if profile is not None else user.id
            send_org_email(
                owner_id,
                subject='Reset your Pulse password',
                message=(
                    f'Someone asked to reset the password for this account.\n\n'
                    f'Reset it here: {reset_link}\n\n'
                    f'If this wasn’t you, you can safely ignore this email.'
                ),
                recipient_list=[email],
            )

        # Same response whether or not the email matched an account — this
        # endpoint must not reveal which emails have accounts.
        return Response({'detail': 'If an account exists for that email, a reset link has been sent.'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            uid = force_str(urlsafe_base64_decode(data['uid']))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({'detail': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, data['token']):
            return Response({'detail': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(data['new_password'], user=user)
        except DjangoValidationError as exc:
            return Response({'new_password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        return Response({'detail': 'Password reset. You can now log in.'})
