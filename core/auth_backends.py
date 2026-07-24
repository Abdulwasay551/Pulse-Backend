from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """Authenticates against either `username` or `email`, whichever the
    login identifier matches — the login form only has one identifier field
    and doesn't ask the user which kind it is.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if identifier is None or password is None:
            return None

        try:
            user = User._default_manager.get(
                Q(**{User.USERNAME_FIELD: identifier}) | Q(email__iexact=identifier)
            )
        except User.DoesNotExist:
            # Run the hasher anyway so login timing doesn't reveal whether
            # the identifier exists (same trick ModelBackend itself uses).
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            user = User._default_manager.filter(
                Q(**{User.USERNAME_FIELD: identifier}) | Q(email__iexact=identifier)
            ).order_by('id').first()

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
