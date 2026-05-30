"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpResponseRedirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from dashboard.views import AdminDashboardView

urlpatterns = [
    path('', lambda r: HttpResponseRedirect('/dashboard/'), name='root'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin/', admin.site.urls),
    path('dashboard/logout/', LogoutView.as_view(next_page='/dashboard/'), name='dashboard_logout'),
    path('users/', include('users.urls')),
    path('wallet/', include('wallet.urls')),
    path('fashion/', include('fashion.urls')),
    path('vtu/', include('vtu.urls')),
    path('api/v1/resellers/', include('vtu.reseller_urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
