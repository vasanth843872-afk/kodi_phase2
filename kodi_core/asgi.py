import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import apps.genealogy.routing



application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(
            apps.genealogy.routing.websocket_urlpatterns
        )
    ),
})
