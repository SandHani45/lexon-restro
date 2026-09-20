"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# core/urls.py

from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.shortcuts import redirect
from django.views.defaults import page_not_found, server_error
from django.views.generic import TemplateView
from core import views

def custom_404(request, exception=None):
    from django.shortcuts import render
    return render(request, "404.html", status=404)

def custom_403(request, exception=None):
    from django.shortcuts import render
    return render(request, "403.html", status=403)

def custom_400(request, exception=None):
    from django.shortcuts import render
    return render(request, "400.html", status=400)

def custom_500(request):
    from django.shortcuts import render
    return render(request, "500.html", status=500)

from django.http import HttpResponse

def robots_txt(request):
    # Same content on every subdomain (this view isn't tenant-aware), which
    # is what we want: the rules below describe the app's URL *shape*, not
    # any one tenant's data, so they apply identically whether requested on
    # lexnorax.net or a real tenant subdomain like spice.lexnorax.net.
    #
    # /menu/ itself is disallowed further down -- it's the staff-facing
    # menu management screen (login-gated, but no reason to spend crawl
    # budget on a login redirect). The two Allow rules for
    # /menu/digital-menu/ and /menu/qr/ below still win over that: Google's
    # own spec matches by the *longest matching path*, not by which rule
    # comes first in the file, so a more specific Allow always overrides a
    # shorter Disallow regardless of order. Those two are the real,
    # public, guest-facing menu pages -- worth being indexable on a
    # tenant's own subdomain (e.g. "Spice Garden menu" becoming
    # searchable), unlike the rest of the app.
    content = """User-agent: *

# Public — the marketing site
Allow: /
Allow: /compare/
Allow: /product-tour/
Allow: /pricing/
Allow: /about/
Allow: /contact/
Allow: /platform/billing/
Allow: /platform/floor-and-kitchen/
Allow: /platform/menu/
Allow: /platform/multi-outlet/
Allow: /platform/inventory/
Allow: /platform/crm/
Allow: /platform/reports/
Allow: /platform/staff/
Allow: /platform/integrations/

# Public — the customer-facing digital menu (overrides the /menu/
# disallow below; see the comment in robots_txt() for why)
Allow: /menu/digital-menu/
Allow: /menu/qr/

# Private app areas — keep crawlers out (these are login-gated anyway)
Disallow: /admin/
Disallow: /superadmin/
Disallow: /dashboard/
Disallow: /setup/
Disallow: /billing/
Disallow: /order/
Disallow: /orders/
Disallow: /pay/
Disallow: /kitchen/
Disallow: /tables/
Disallow: /reports/
Disallow: /inventory/
Disallow: /crm/
Disallow: /shifts/
Disallow: /accounts/
Disallow: /portal/
Disallow: /agency/
Disallow: /menu/

Sitemap: https://lexnorax.net/sitemap.xml"""
    return HttpResponse(content, content_type='text/plain')

def sitemap_xml(request):
    from django.utils import timezone
    # Public, indexable marketing pages (served as static files by
    # WhiteNoise from public/, see WHITENOISE_ROOT in settings.py) --
    # add an entry here whenever a new one ships.
    # lastmod is today's date, generated fresh on every request, rather
    # than a hand-typed date that goes stale the moment anyone forgets to
    # update it (it had drifted to a 3-month-old date before this fix).
    today = timezone.localdate().isoformat()
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://lexnorax.net/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/compare/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/product-tour/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/pricing/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/about/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/contact/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/billing/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/floor-and-kitchen/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/menu/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/multi-outlet/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/inventory/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/crm/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/reports/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/staff/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://lexnorax.net/platform/integrations/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
</urlset>"""
    return HttpResponse(content, content_type='application/xml')

handler400 = "core.urls.custom_400"
handler403 = "core.urls.custom_403"
handler404 = "core.urls.custom_404"
handler500 = "core.urls.custom_500"

urlpatterns = [

    path(settings.ADMIN_URL, admin.site.urls),

    # default redirect — authenticated → dashboard, anonymous → login
    path('', views.landing, name='landing'),

    # Health check
    path('health/', views.health_check, name='health_check'),
    # Demo tenant switcher — DEBUG only, 404 in production
    path('demo/', views.demo_switch, name='demo_switch'),
    path('robots.txt', robots_txt),
    path('sitemap.xml', sitemap_xml),
    # Public marketing page — showcases the post-login product experience
    # (mockup screenshots only; never the real authenticated dashboard).
    path('product-tour/', TemplateView.as_view(template_name='core/product_tour.html'), name='product_tour'),
    # Public marketing pages — dedicated pricing/about/contact + per-feature
    # platform deep-dives, mirroring sevenrooms.com's page breadth. All
    # additive; none of this touches the real authenticated app.
    path('pricing/', TemplateView.as_view(template_name='core/pricing.html'), name='pricing'),
    path('about/', TemplateView.as_view(template_name='core/about.html'), name='about'),
    path('contact/', TemplateView.as_view(template_name='core/contact.html'), name='contact'),
    path('platform/billing/', TemplateView.as_view(template_name='core/platform_billing.html'), name='platform_billing'),
    path('platform/floor-and-kitchen/', TemplateView.as_view(template_name='core/platform_floor_kitchen.html'), name='platform_floor_kitchen'),
    path('platform/menu/', TemplateView.as_view(template_name='core/platform_menu.html'), name='platform_menu'),
    path('platform/multi-outlet/', TemplateView.as_view(template_name='core/platform_multi_outlet.html'), name='platform_multi_outlet'),
    path('platform/inventory/', TemplateView.as_view(template_name='core/platform_inventory.html'), name='platform_inventory'),
    path('platform/crm/', TemplateView.as_view(template_name='core/platform_crm.html'), name='platform_crm'),
    path('platform/reports/', TemplateView.as_view(template_name='core/platform_reports.html'), name='platform_reports_page'),
    path('platform/staff/', TemplateView.as_view(template_name='core/platform_staff.html'), name='platform_staff'),
    path('platform/integrations/', TemplateView.as_view(template_name='core/platform_integrations.html'), name='platform_integrations'),
    # /compare/petpooja/ existed for ~6 minutes on 2026-07-31 before being
    # genericized back to /compare/ (af74912) -- if Google indexed it in
    # that window, this stops it dead-ending in a 404 and consolidates any
    # indexing signal onto the page that actually exists now.
    path('compare/petpooja/', lambda r: redirect('/compare/', permanent=True)),
    path('favicon.ico', lambda r: HttpResponse(status=204)),
    # PWA
    path('sw.js', views.serve_sw, name='service_worker'),
    path('manifest.json', TemplateView.as_view(template_name='manifest.json', content_type='application/manifest+json')),

    # apps
    path('', include('accounts.urls')),
    path('', include('orders.urls')),
    path('', include('promos.urls')),
    path('', include('printing.urls')),
    path('', include('tokens.urls')),
    path('', include('kitchen.urls')),
    path('', include('waiter.urls')),
    path('', include('tablemerge.urls')),
    path('', include('payments.urls')),

    
    # menu module
    path('menu/', include('menu.urls')),

    # reports module
    path('reports/', include('reports.urls')),

    # inventory module
    path('inventory/', include('inventory.urls')),
    
    # setup module
    path('setup/', include('setup.urls')),

    # shifts module
    path('shifts/', include('shifts.urls')),

    # crm module
    path('crm/', include('crm.urls')),

    # EasyBillBro's own subscription billing (charging tenants, not tenant-facing)
    path('billing/', include('billing.urls')),

    # finance module
    path('finance/', include('finance.urls')),

    # agency module
    path('agency/', include('agency.urls')),

    # portal — EasyBillBro internal ops panel
    path('portal/', include('portal.urls', namespace='portal')),
    # backward compat: /superuser/ → /portal/
    path('superuser/', lambda r: __import__('django.shortcuts', fromlist=['redirect']).redirect('/portal/')),
    path('superuser/tenant/<int:tenant_id>/', lambda r, tenant_id: __import__('django.shortcuts', fromlist=['redirect']).redirect(f'/portal/tenant/{tenant_id}/')),

    # notifications module
    path('', include('notifications.urls')),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Catch-all route: prevents technical debug code error screens on any router
urlpatterns += [
    re_path(r'^.*$', custom_404, name='catch_all_404'),
]