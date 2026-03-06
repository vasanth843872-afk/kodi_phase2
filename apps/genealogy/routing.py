from django.urls import re_path
from .consumers import invitation_consumer, acceptance_consumer

websocket_urlpatterns = [
    re_path(
        r'ws/invitations/$',
        invitation_consumer.InvitationConsumer.as_asgi()
    ),
    re_path(
        r'ws/invitations/accept/(?P<token>[^/]+)/$',
        acceptance_consumer.InvitationAcceptanceConsumer.as_asgi()
    ),
]
