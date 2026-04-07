"""
kodi_core/asgi.py — updated to include chat WebSocket routing.
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kodi_core.settings")

django_asgi_app = get_asgi_application()

# Import AFTER Django setup
from apps.chat.middleware import JWTAuthMiddlewareStack
from apps.chat.routing import websocket_urlpatterns as chat_ws
from apps.genealogy.routing import websocket_urlpatterns as genealogy_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            chat_ws + genealogy_ws   # combine all WS routes
        )
    ),
})