from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


from apps.genealogy.consumers import invitation_consumer, acceptance_consumer
from django.urls import re_path

# Add at the top of urls.py
import sys
from django.core.exceptions import ImproperlyConfigured




urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/profiles/', include('apps.profiles.urls')),
    path('api/families/', include('apps.families.urls')),
    path('api/relations/', include('apps.relations.urls')),
    path('api/genealogy/', include('apps.genealogy.urls')),
    path('api/event_management/', include('apps.event_management.urls')),
    path('api/admin/', include('admin_app.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    
    # path('api/chat/', include('apps.chat.urls')),
    # path('api/posts/', include('apps.posts.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
