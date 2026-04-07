from rest_framework.permissions import IsAdminUser
from rest_framework import status
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import *

# Admin: List all chat rooms (with optional filters)
class AdminRoomListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = ChatRoomSerializer
    queryset = ChatRoom.objects.all().order_by('-created_at')

# Admin: Delete any message (hard delete)
class AdminDeleteMessageView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, message_id):
        msg = get_object_or_404(Message, id=message_id)
        msg.delete()  # hard delete
        return Response({'detail': 'Message permanently deleted.'})

# Admin: List all users with block/chat stats
# views.py – AdminUserListView
class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = UserAdminSerializer
    def get_queryset(self):
        # Use select_related to fetch UserProfile in the same query
        return User.objects.all().select_related('profile').order_by('-created_at')
        # Change 'userprofile' to your actual related_name
    # queryset = User.objects.all().order_by('-created_at')  # fix here

# Admin: Force user to leave a group or remove any member
class AdminRemoveFromGroupView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

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
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = BlockedUserSerializer
    queryset = BlockedUser.objects.all().select_related('blocker', 'blocked')