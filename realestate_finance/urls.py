from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.urls import include, path
from django.views.static import serve


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("media/<path:path>", login_required(serve), {"document_root": settings.MEDIA_ROOT}, name="protected_media"),
    path("", include("portfolio.urls")),
]
