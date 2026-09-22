# core/context_processors.py
from django.conf import settings

def base_url(request):
    return {'BASE_URL': settings.BASE_URL}

def app_version(request):
    from core.version import APP_VERSION
    return {'APP_VERSION': APP_VERSION}

def currency(request):
    """
    Tenant-aware currency symbol for every operational template (₹ for
    India, AED for UAE, etc.) — see tenants/tax_regimes.py, the single
    source of truth this reads from via Outlet.currency_symbol. Falls back
    to India's ₹ for logged-out/no-outlet requests (public bill links,
    login page) since that's this app's default market.
    """
    outlet = getattr(getattr(request, 'user', None), 'outlet', None)
    symbol = outlet.currency_symbol if outlet else "₹"
    return {'CURRENCY_SYMBOL': symbol}

def tenant_features(request):
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'tenant_features': [], 'tenant_type': 'fine_dining'}

    tenant = getattr(request.user, 'tenant', None)
    if not tenant:
        return {'tenant_features': [], 'tenant_type': 'fine_dining'}

    from core.features import has_feature, get_all_known_features

    # Use the canonical feature list from FEATURE_GROUPS so custom-only features
    # (multi_kitchen, loyalty_points, etc.) are evaluated for tenants that have
    # overrides enabling them — not just the TENANT_FEATURES defaults.
    resolved_features = [f for f in get_all_known_features() if has_feature(tenant, f)]

    return {
        'tenant_features': resolved_features,
        'tenant_type': tenant.tenant_type,
    }

