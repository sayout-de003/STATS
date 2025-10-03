# users/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Called on connection.
        # To accept the connection call:
        await self.accept()

    async def disconnect(self, close_code):
        # Called when the socket closes
        pass

    async def receive(self, text_data):
        # Called with a new message from the client
        pass