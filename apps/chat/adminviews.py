from django.db.models import Count, Q, Max
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import IsAdminUser,IsAuthenticated
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import *
from admin_app.permissions import CanManageChat,CanManagePost


# Admin: List all chat rooms (with optional filters)
class AdminRoomListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated,CanManageChat]
    serializer_class = ChatRoomSerializer
    queryset = ChatRoom.objects.all().order_by('-created_at')

# Admin: Delete any message (hard delete)
class AdminDeleteMessageView(APIView):
    permission_classes = [IsAuthenticated,CanManageChat]

    def delete(self, request, message_id):
        msg = get_object_or_404(Message, id=message_id)
        msg.delete()  # hard delete
        return Response({'detail': 'Message permanently deleted.'})

# Admin: List all users with block/chat stats
# views.py – AdminUserListView
class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated,CanManageChat]
    serializer_class = UserAdminSerializer
    def get_queryset(self):
        # Use select_related to fetch UserProfile in the same query
        return User.objects.all().select_related('profile').order_by('-created_at')
        # Change 'userprofile' to your actual related_name
    # queryset = User.objects.all().order_by('-created_at')  # fix here

# Admin: Force user to leave a group or remove any member
class AdminRemoveFromGroupView(APIView):
    permission_classes = [IsAuthenticated,CanManageChat]

    def post(self, request, room_id, user_id):
        room = get_object_or_404(ChatRoom, id=room_id, room_type='group')
        user = get_object_or_404(User, id=user_id)
        membership = ChatRoomMember.objects.filter(room=room, user=user)
        if not membership.exists():
            return Response({'detail': 'User not in group.'}, status=404)
        membership.delete()
        room.members.remove(user)
        return Response({'detail': f'User {user_id} removed from group.'})

# Admin: View all blocked entries
class AdminBlockedList(generics.ListAPIView):
    permission_classes = [IsAuthenticated,CanManageChat]
    serializer_class = BlockedUserSerializer
    queryset = BlockedUser.objects.all().select_related('blocker', 'blocked')
    
class AdminStatsView(APIView):
    """
    GET /api/chat/admin/stats/
    Returns platform statistics for admin users.
    """
    permission_classes = [CanManageChat]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        # User stats – use created_at instead of date_joined
        total_users = User.objects.filter(is_active=True).count()
        new_users_today = User.objects.filter(created_at__gte=today_start).count()
        new_users_last_7d = User.objects.filter(created_at__gte=week_ago).count()

        # Chat room stats
        total_rooms = ChatRoom.objects.count()
        direct_rooms = ChatRoom.objects.filter(room_type='direct').count()
        group_rooms = ChatRoom.objects.filter(room_type='group').count()

        # Message stats
        total_messages = Message.objects.filter(is_deleted=False).count()
        messages_today = Message.objects.filter(created_at__gte=today_start, is_deleted=False).count()
        messages_last_7d = Message.objects.filter(created_at__gte=week_ago, is_deleted=False).count()

        # Attachment stats
        total_attachments = MessageAttachment.objects.count()
        attachments_today = MessageAttachment.objects.filter(
            message__created_at__gte=today_start
        ).count()

        # Most active rooms (top 5 by message count)
        active_rooms = (
            ChatRoom.objects.annotate(msg_count=Count('messages', filter=Q(messages__is_deleted=False)))
            .order_by('-msg_count')[:5]
            .values('id', 'name', 'room_type', 'msg_count')
        )

        # Most active users (top 5 by message count)
        active_users = (
            User.objects.filter(is_active=True)
            .annotate(msg_count=Count('sent_messages', filter=Q(sent_messages__is_deleted=False)))
            .order_by('-msg_count')[:5]
            .values('id', 'mobile_number', 'msg_count')
        )

        stats = {
            "users": {
                "total_active": total_users,
                "new_today": new_users_today,
                "new_last_7_days": new_users_last_7d,
            },
            "chat_rooms": {
                "total": total_rooms,
                "direct": direct_rooms,
                "group": group_rooms,
            },
            "messages": {
                "total": total_messages,
                "today": messages_today,
                "last_7_days": messages_last_7d,
            },
            "attachments": {
                "total": total_attachments,
                "today": attachments_today,
            },
            "top_5_active_rooms": list(active_rooms),
            "top_5_active_users": list(active_users),
        }
        return Response(stats)
    
    
class AdminUserChatStatusView(generics.ListAPIView):
    permission_classes = [CanManageChat]
    serializer_class = UserChatStatusSerializer

    def get_queryset(self):
        return (
            User.objects
            .filter(is_active=True)
            .annotate(
                total_messages=Count('sent_messages', filter=Q(sent_messages__is_deleted=False)),
                total_rooms=Count('chat_rooms', distinct=True),
                last_message_at=Max('sent_messages__created_at', filter=Q(sent_messages__is_deleted=False)),
                blocked_by_count=Count('blocked_by', distinct=True),
                has_blocked_count=Count('blocking', distinct=True),
            )
            .filter(total_messages__gt=0)          # only users with at least one sent message
            .order_by('-last_message_at')
        )