from django.urls import re_path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    # Direct & group rooms — same consumer, room_id is the discriminator
    re_path(r"ws/chat/(?P<room_id>\d+)/$", ChatConsumer.as_asgi()),
]