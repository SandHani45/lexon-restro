# webstore/models.py
from django.db import models


class CustomerAccount(models.Model):
    """
    A self-service login for the browser-based, no-QR ordering flow
    (easybillbro.com/<restaurant-slug>/). Deliberately NOT a
    TenantScopedModel and NEVER assigned to request.user -- this app's
    entire session/identity mechanism (see webstore/auth.py) is kept fully
    separate from accounts.User (the staff/AUTH_USER_MODEL) specifically
    so that ContextLoggingMiddleware's tenant auto-scoping (which is keyed
    off request.user.tenant/request.user.outlet, not request.tenant) is
    never put in a position where a customer session could reach it. One
    account works across every participating restaurant, matching how a
    real food-delivery app account behaves -- it is not tied to a single
    tenant.
    """
    username = models.CharField(max_length=150, unique=True)
    password_hash = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["username"], name="webstore_cust_username_idx"),
        ]

    def __str__(self):
        return self.username
