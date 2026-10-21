"""User manager for the email-login custom User (User.objects)."""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the email-based custom User (create_user/create_superuser).

    use_in_migrations keeps historical migrations pointing at this class,
    matching Django's own UserManager convention.
    """

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular active user (email normalized)."""
        if not email:
            raise ValueError("The Email field must be set")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create an active staff superuser; refuses incomplete flags."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)
