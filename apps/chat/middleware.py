"""
JWT WebSocket Authentication Middleware.

Usage in asgi.py:
    from apps.chat.middleware import JWTAuthMiddlewareStack
    application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))

The middleware reads the JWT token from:
  1. Query param:  ws://host/ws/chat/123/?token=<access_token>
  2. Subprotocol:  passed as Authorization header alternative (mobile clients)

After validation, scope['user'] is set just like a normal authenticated request.
"""

from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_key):
    try:
        # Validate token
        UntypedToken(token_key)
        decoded = jwt_decode(token_key, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = decoded.get("user_id")
        return User.objects.get(id=user_id)
    except (InvalidToken, TokenError, User.DoesNotExist, Exception):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Attach the authenticated user to the WebSocket scope."""

    async def __call__(self, scope, receive, send):
        # Try query param first: ?token=xxx
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token = None

        if "token" in params:
            token = params["token"][0]

        # Try Authorization header (some clients send this)
        if not token:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]

        scope["user"] = await get_user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)