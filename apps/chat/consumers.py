"""
ChatConsumer — handles real-time messaging over WebSocket.

Channel group naming:
  - Direct room:  chat_room_<room_id>
  - Group room:   chat_room_<room_id>   (same — room ID is the discriminator)

Flow:
  connect    → authenticate → join channel group → send last 30 messages
  receive    → save to DB   → broadcast to group
  disconnect → leave group
  
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from .models import ChatRoom, Message, MessageReadStatus


class ChatConsumer(AsyncWebsocketConsumer):

    # ------------------------------------------------------------------ connect
    async def connect(self):
        print("✅ CONNECT CALLED")
        print("USER:", self.scope.get("user"))
        print("IS AUTH:", getattr(self.scope.get("user"), "is_authenticated", None))
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_room_{self.room_id}"
        self.user = self.scope.get("user")

        # Reject unauthenticated connections
        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        # Verify user is a member of this room
        is_member = await self.check_membership(self.room_id, self.user)
        if not is_member:
            await self.close(code=4003)
            return

        # Join the channel group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        await self.channel_layer.group_send(
        self.room_group_name,
        {
            "type": "user_status",
            "user_id": self.user.id,
            "status": "online",
        },
    )

        # Send last 30 messages on connect
        history = await self.get_message_history(self.room_id)
        await self.send(text_data=json.dumps({
            "type": "history",
            "messages": history,
        }))

    # --------------------------------------------------------------- disconnect
    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_status",
                    "user_id": self.user.id,
                    "status": "offline",
                },
            )
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # ------------------------------------------------------------------ receive
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "message")

        if msg_type == "message":
            content = data.get("content", "").strip()
            if not content:
                return

            # --- BLOCK CHECK ---
            # Get the other members of this room
            other_members = await self.get_other_members(self.room_id, self.user)
            for other_user in other_members:
                if await self.is_blocked(self.user, other_user):
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "detail": "You cannot send messages to a user you have blocked.",
                    }))
                    return
                if await self.is_blocked(other_user, self.user):
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "detail": "You cannot send messages to this user.",
                    }))
                    return
            # --- END BLOCK CHECK ---

            # Persist to DB
            message = await self.save_message(self.room_id, self.user, content)

            # Broadcast to everyone in the room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message_id": message["id"],
                    "content": message["content"],
                    "sender_id": message["sender_id"],
                    "sender_mobile": message["sender_mobile"],
                    "created_at": message["created_at"],
                },
            )

        elif msg_type == "read":
            message_id = data.get("message_id")
            if message_id:
                await self.mark_read(message_id, self.user)

        elif msg_type == "typing":
            # Broadcast typing indicator (not persisted)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "sender_id": self.user.id,
                    "sender_mobile": self.user.mobile_number,
                    "is_typing": data.get("is_typing", True),
                },
            )
            
        elif msg_type == "read":
            message_id = data.get("message_id")
            if message_id:
                await self.mark_read(message_id, self.user)

                # 🔥 Broadcast seen event
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "message_seen",
                        "message_id": message_id,
                        "seen_by": self.user.id,
                    },
                )

    # -------------------------------------------------- group message handlers
    async def chat_message(self, event):
        """Called when a message is broadcast to the group."""
        await self.send(text_data=json.dumps({
            "type": "message",
            "message_id": event["message_id"],
            "content": event["content"],
            "sender_id": event["sender_id"],
            "sender_mobile": event["sender_mobile"],
            "created_at": event["created_at"],
        }))

    async def typing_indicator(self, event):
        """Forward typing indicators to the client."""
        # Don't send back to the typing user themselves
        if event["sender_id"] != self.user.id:
            await self.send(text_data=json.dumps({
                "type": "typing",
                "sender_id": event["sender_id"],
                "sender_mobile": event["sender_mobile"],
                "is_typing": event["is_typing"],
            }))
            
    async def user_status(self, event):
    # Don't send back to same user
        if event["user_id"] != self.user.id:
            await self.send(text_data=json.dumps({
                "type": "status",
                "user_id": event["user_id"],
                "status": event["status"],
            }))
            
    async def message_seen(self, event):
        # Don't send back to the same user
        if event["seen_by"] != self.user.id:
            await self.send(text_data=json.dumps({
                "type": "seen",
                "message_id": event["message_id"],
                "seen_by": event["seen_by"],
            }))

    # ---------------------------------------------------------- DB helpers
    @database_sync_to_async
    def check_membership(self, room_id, user):
        return ChatRoom.objects.filter(id=room_id, members=user).exists()

    @database_sync_to_async
    def save_message(self, room_id, user, content):
        room = ChatRoom.objects.get(id=room_id)
        msg = Message.objects.create(room=room, sender=user, content=content)
        return {
            "id": msg.id,
            "content": msg.content,
            "sender_id": user.id,
            "sender_mobile": user.mobile_number,
            "created_at": msg.created_at.isoformat(),
        }

    @database_sync_to_async
    def get_message_history(self, room_id, limit=30):
        messages = (
            Message.objects
            .filter(room_id=room_id, is_deleted=False)
            .select_related("sender")
            .order_by("-created_at")[:limit]
        )
        return [
            {
                "id": m.id,
                "content": m.content,
                "sender_id": m.sender_id,
                "sender_mobile": m.sender.mobile_number if m.sender else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(list(messages))
        ]

    @database_sync_to_async
    def mark_read(self, message_id, user):
        MessageReadStatus.objects.get_or_create(message_id=message_id, user=user)

    # New helpers for block checks
    @database_sync_to_async
    def get_other_members(self, room_id, user):
        from apps.chat.models import ChatRoom
        room = ChatRoom.objects.get(id=room_id)
        return list(room.members.exclude(id=user.id))

    @database_sync_to_async
    def is_blocked(self, blocker, blocked):
        from apps.chat.models import BlockedUser
        return BlockedUser.objects.filter(blocker=blocker, blocked=blocked).exists()