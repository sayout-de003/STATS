from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Add your websocket URL patterns here
    # Example:
    # re_path(r'ws/chat/(?P<room_name>\w+)/$', consumers.ChatConsumer.as_asgi()),
     re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
