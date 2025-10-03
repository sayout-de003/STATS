import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stats_project.settings")
django.setup()
django_asgi_app = get_asgi_application()

# import your websocket routes (create later)
from channels.auth import AuthMiddlewareStack
import users.routing  # example

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            users.routing.websocket_urlpatterns
        )
    ),
})
