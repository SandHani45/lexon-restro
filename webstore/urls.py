# webstore/urls.py
from django.urls import path
from . import views

# Mounted at core/urls.py under path('<slug:tenant_slug>/', include(...)),
# so every route below automatically receives tenant_slug as a kwarg.
urlpatterns = [
    path("", views.store_home, name="webstore_home"),
    path("login/", views.customer_login, name="webstore_login"),
    path("register/", views.customer_register, name="webstore_register"),
    path("logout/", views.customer_logout, name="webstore_logout"),
    path("create-order/", views.create_web_order, name="webstore_create_order"),
]
