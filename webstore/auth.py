# webstore/auth.py
"""
Session-based identity for webstore.CustomerAccount, kept entirely separate
from django.contrib.auth / request.user (the staff login). See the
CustomerAccount docstring for why this separation is load-bearing, not
stylistic -- request.user driving TenantScopedModel auto-scoping means a
customer session must never be assigned to it.
"""
from .models import CustomerAccount

SESSION_KEY = "webstore_customer_id"


def login_customer(request, customer):
    request.session[SESSION_KEY] = customer.id


def logout_customer(request):
    request.session.pop(SESSION_KEY, None)


def get_current_customer(request):
    customer_id = request.session.get(SESSION_KEY)
    if not customer_id:
        return None
    return CustomerAccount.objects.filter(id=customer_id).first()
