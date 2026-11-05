from django.conf import settings
from django.db import models
from django.utils import timezone


class PrivacyConsent(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="privacy_consent")
    accepted_at = models.DateTimeField(default=timezone.now)
    policy_version = models.CharField(max_length=20, default="1.0")

    def __str__(self):
        return f"Autorización de {self.user.email}"


class Household(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_households")
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    ROLE_CHOICES = [
        (ADMIN, "Administrador"),
        (MEMBER, "Miembro"),
    ]

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="household_memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["household", "user"], name="unique_household_membership")
        ]
        ordering = ["joined_at", "id"]

    def __str__(self):
        return f"{self.user.email} - {self.household.name}"
