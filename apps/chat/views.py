from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.generics import ListAPIView
from .utils import _get_profile_image,_get_profile_name
from rest_framework.parsers import MultiPartParser, FormParser
from .models import *
from .serializers import *
from django.http import FileResponse

User = get_user_model()


class RoomListView(generics.ListAPIView):
    """GET /api/chat/rooms/ — list all rooms the current user belongs to."""
    serializer_class = ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ChatRoom.objects.filter(members=self.request.user)
        
        # Add filtering by room_type query parameter
        room_type = self.request.query_params.get('type')
        if room_type in ['direct', 'group']:
            queryset = queryset.filter(room_type=room_type)
            
        return queryset.prefetch_related("members").order_by("-updated_at")


class CreateDirectRoomView(APIView):
    """POST /api/chat/rooms/direct/ — get or create a DM room."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateDirectRoomSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        target = get_object_or_404(User, id=serializer.validated_data["target_user_id"])
        room, created = ChatRoom.get_or_create_direct_room(request.user, target)

        return Response(
            ChatRoomSerializer(room, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CreateGroupRoomView(APIView):
    """POST /api/chat/rooms/group/ — create a group chat."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateGroupRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        member_ids = serializer.validated_data["member_ids"]
        members = User.objects.filter(id__in=member_ids, is_active=True)

        room = ChatRoom.objects.create(
            room_type="group",
            name=serializer.validated_data["name"],
        )

        # Creator = admin
        ChatRoomMember.objects.create(
            room=room,
            user=request.user,
            role="admin"
        )
        member_users = [request.user] + list(members)  
        # Add members
        for user in members:
            if user != request.user:  # avoid duplicate creator
                ChatRoomMember.objects.create(
                    room=room,
                    user=user,
                    role="member"
                )
        room.members.add(*member_users)
        return Response(
            ChatRoomSerializer(room, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

# class MessageListView(generics.ListAPIView):
#     """GET /api/chat/rooms/<room_id>/messages/?page=1 — paginated message history."""
#     serializer_class = MessageSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         room_id = self.kwargs["room_id"]
#         # Ensure user is a member
#         get_object_or_404(ChatRoom, id=room_id, members=self.request.user)
#         return (
#             Message.objects
#             .filter(room_id=room_id, is_deleted=False)
#             .select_related("sender")
#             .order_by("-created_at")
#         )


class MarkRoomReadView(APIView):
    """POST /api/chat/rooms/<room_id>/read/ — mark all messages as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(ChatRoom, id=room_id, members=request.user)
        messages = room.messages.filter(is_deleted=False).exclude(sender=request.user)
        objs = [
            MessageReadStatus(message=m, user=request.user)
            for m in messages
        ]
        MessageReadStatus.objects.bulk_create(objs, ignore_conflicts=True)
        return Response({"detail": "Marked as read."})
    
    
class BlockUserView(APIView):
    """
    POST /api/accounts/block/
    Block a user by their ID.
    If already blocked, returns 200 (idempotent).
    """
    permission_classes = [IsAuthenticated]
 
    def post(self, request):
        serializer = BlockUserSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
 
        target = get_object_or_404(User, id=serializer.validated_data['user_id'])
 
        block, created = BlockedUser.objects.get_or_create(
            blocker=request.user,
            blocked=target,
        )
 
        return Response(
            {
                "detail": f"User {target.mobile_number} blocked successfully."
                          if created else f"User {target.mobile_number} is already blocked.",
                "blocked_id": target.id,
                "blocked_mobile": target.mobile_number,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
 
 
class UnblockUserView(APIView):
    """
    POST /api/accounts/unblock/
    Unblock a previously blocked user.
    """
    permission_classes = [IsAuthenticated]
 
    def post(self, request):
        serializer = BlockUserSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
 
        target = get_object_or_404(User, id=serializer.validated_data['user_id'])
 
        deleted_count, _ = BlockedUser.objects.filter(
            blocker=request.user,
            blocked=target,
        ).delete()
 
        if deleted_count:
            return Response(
                {
                    "detail": f"User {target.mobile_number} unblocked successfully.",
                    "blocked_id": target.id,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {"detail": "This user was not blocked."},
            status=status.HTTP_404_NOT_FOUND,
        )
 
 
class BlockedUserListView(APIView):
    """
    GET /api/accounts/blocked/
    Returns the list of users the current user has blocked.
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        blocks = (
            BlockedUser.objects
            .filter(blocker=request.user)
            .select_related('blocked')
            .order_by('-created_at')
        )
        serializer = BlockedUserSerializer(blocks, many=True)
        return Response(serializer.data)
 
 
class BlockStatusView(APIView):
    """
    GET /api/accounts/block-status/<user_id>/
    Check if the current user has blocked (or been blocked by) a specific user.
    Useful before opening a chat.
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request, user_id):
        target = get_object_or_404(User, id=user_id, is_active=True)
 
        i_blocked_them = BlockedUser.objects.filter(
            blocker=request.user, blocked=target
        ).exists()
 
        they_blocked_me = BlockedUser.objects.filter(
            blocker=target, blocked=request.user
        ).exists()
 
        return Response({
            "user_id": target.id,
            "mobile_number": target.mobile_number,
            "i_blocked_them": i_blocked_them,
            "they_blocked_me": they_blocked_me,
            "chat_allowed": not i_blocked_them and not they_blocked_me,
        })
        
class UpdateMessageView(APIView):
    """
    PUT /api/chat/messages/<message_id>/edit/  — edit your own message
    """
    permission_classes = [IsAuthenticated]

    def put(self, request, message_id):
        msg = get_object_or_404(Message, id=message_id, sender=request.user, is_deleted=False)
        
        serializer = MessageUpdateSerializer(msg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        msg.content = serializer.validated_data['content']
        msg.is_edited = True
        msg.edited_at = timezone.now()
        msg.save(update_fields=['content', 'is_edited', 'edited_at'])
        
        return Response({
            'detail': 'Message updated.',
            'message': MessageSerializer(msg).data  # reuse your existing serializer
        })
        
        
class DeleteMessageView(APIView):
    """DELETE /api/chat/messages/<message_id>/ — soft delete own message."""
    permission_classes = [IsAuthenticated]
 
    def delete(self, request, message_id):
        msg = get_object_or_404(Message, id=message_id, sender=request.user)
        msg.is_deleted = True
        msg.deleted_at = timezone.now()
        msg.save(update_fields=['is_deleted', 'deleted_at'])
        return Response({'detail': 'Message deleted.'})
    

class ContactNicknameView(APIView):
    """
    GET  /api/chat/contacts/       — list all contacts with nicknames
    POST /api/chat/contacts/       — set or update nickname for a contact
    DELETE /api/chat/contacts/<id>/ — remove nickname
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        nicknames = ContactNickname.objects.filter(owner=request.user).select_related('contact', 'contact__profile')
        data = [
            {
                'contact_id': n.contact.id,
                'mobile_number': n.contact.mobile_number,
                'nickname': n.nickname,
                'profile_name': _get_profile_name(n.contact),
                'profile_image': _get_profile_image(n.contact, request),
            }
            for n in nicknames
        ]
        return Response(data)
 
    def post(self, request):
        serializer = ContactNicknameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = get_object_or_404(User, id=serializer.validated_data['contact_id'])
        obj, _ = ContactNickname.objects.update_or_create(
            owner=request.user, contact=contact,
            defaults={'nickname': serializer.validated_data['nickname']},
        )
        return Response({'detail': 'Nickname saved.', 'nickname': obj.nickname})
 
    def delete(self, request, contact_id):
        ContactNickname.objects.filter(owner=request.user, contact_id=contact_id).delete()
        return Response({'detail': 'Nickname removed.'})
    
# helper method

 



#clear chat
class ClearChatView(APIView):
    """POST /api/chat/rooms/<room_id>/clear/ — clear chat for this user only."""
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        # Ensure the user is a member of the room
        room = get_object_or_404(ChatRoom, id=room_id, members=request.user)
        # Get or create the membership record
        membership, _ = ChatRoomMember.objects.get_or_create(
            room=room,
            user=request.user,
            defaults={'role': 'member'}  # default role if not set
        )
        membership.cleared_at = timezone.now()
        membership.save(update_fields=['cleared_at'])
        return Response({'detail': 'Chat cleared for you.'})


# add an member in group
class AddGroupMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(ChatRoom, id=room_id, room_type="group")

        # Check admin
        if not ChatRoomMember.objects.filter(
            room=room, user=request.user, role="admin"
        ).exists():
            return Response({"detail": "Only admins can add members."}, status=403)

        member_ids = request.data.get("member_ids", [])
        try:
            member_ids = [int(id) for id in member_ids]
        except ValueError:
            return Response({"detail": "Invalid member ID format."}, status=400)
        users = User.objects.filter(id__in=member_ids)

        # Fetch users
        # users = User.objects.filter(id__in=member_ids, is_active=True)

        # Find missing IDs
        found_ids = set(users.values_list("id", flat=True))
        missing_ids = set(member_ids) - found_ids

        # 🚨 IMPORTANT: Throw error if any user not found
        if missing_ids:
            return Response(
                {
                    "detail": "User not found",
                    "missing_ids": list(missing_ids)
                },
                status=404
            )
        created_members = []
        for user in users:
            obj, created = ChatRoomMember.objects.get_or_create(
                room=room,
                user=user,
                defaults={
                    "role": "member",
                    
                }
            )
            if created:
                created_members.append(user.id)
                
        room.members.add(*[u for u in users if u.id in created_members])

        return Response({
            "detail": "Members processed.",
            "added": created_members
        })
    
# remove the member from group
class RemoveGroupMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(ChatRoom, id=room_id, room_type="group")

        if not ChatRoomMember.objects.filter(
            room=room, user=request.user, role="admin"
        ).exists():
            return Response({"detail": "Only admins can remove members."}, status=403)

        member_ids = request.data.get("member_ids", [])

        if request.user.id in member_ids:
            return Response(
                {"detail": "Use leave API to exit group."},
                status=400
            )

        deleted_count, _ = ChatRoomMember.objects.filter(
            room=room,
            user_id__in=member_ids
        ).delete()

        return Response({
            "detail": "Members removed.",
            "removed_count": deleted_count
        })
    

class LeaveGroupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(ChatRoom, id=room_id, room_type="group")

        membership = ChatRoomMember.objects.filter(
            room=room, user=request.user
        ).first()

        if not membership:
            return Response({"detail": "Not a member."}, status=404)

        # Auto-assign new admin if needed
        if membership.role == "admin":
            admins = ChatRoomMember.objects.filter(room=room, role="admin")

            if admins.count() == 1:
                new_admin = ChatRoomMember.objects.filter(
                    room=room
                ).exclude(user=request.user).first()

                if new_admin:
                    new_admin.role = "admin"
                    new_admin.save(update_fields=["role"])

        membership.delete()
        room.members.remove(request.user)

        return Response({"detail": "You left the group."})
    

    
# view all members in a group
class GroupMembersView(ListAPIView):
    """
    GET /api/chat/rooms/<room_id>/members/
    List all members of a group (including admins).
    """
    serializer_class = GroupMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        room_id = self.kwargs['room_id']
        # Ensure the requesting user is a member of the room
        room = get_object_or_404(ChatRoom, id=room_id, room_type='group', members=self.request.user)
        return ChatRoomMember.objects.filter(room=room).select_related('user')
    
    
# class CreateMessageView(APIView):
#     """
#     POST /api/chat/rooms/<room_id>/messages/
#     Creates a new message in the room with optional file attachments.
#     """
    
#     permission_classes = [IsAuthenticated]
#     parser_classes = [MultiPartParser, FormParser]  # to handle file uploads

#     def post(self, request, room_id):
#         room = get_object_or_404(ChatRoom, id=room_id, members=request.user)

#         # Blocking checks (if you have BlockedUser model)
#         # Check if the user has blocked anyone in the room? Typically handled at message creation.
#         # For simplicity, we assume room membership already ensures they can talk.

#         serializer = MessageCreateSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         message = serializer.save(room=room, sender=request.user)

#         # Return the full message data
#         output_serializer = MessageSerializer(message, context={'request': request})
#         return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
class DownloadAttachmentView(APIView):
    """
    GET /api/chat/attachments/<attachment_id>/download/
    Returns the file for download.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, attachment_id):
        attachment = get_object_or_404(MessageAttachment, id=attachment_id)
        message = attachment.message

        # Ensure the user is a member of the room
        if not message.room.members.filter(id=request.user.id).exists():
            return Response(
                {"detail": "You are not a member of this chat room."},
                status=status.HTTP_403_FORBIDDEN
            )

        # If message is deleted, maybe hide attachments? We'll still allow download if the file exists.
        # Optional: check if the user has cleared the chat etc.

        # Return the file
        
        response = FileResponse(
            attachment.file.open('rb'),
            content_type=attachment.content_type,
            as_attachment=True,
            filename=attachment.filename
        )
        return response
        # response['Content-Disposition'] = f'attachment; filename="{attachment.filename}"'
        # print("CONTENT TYPE:", attachment.content_type)
        # print("FILE NAME:", attachment.filename)
        # print("FILE PATH:", attachment.file.path)
        # return response
    
    
class MessageView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # for file uploads

    def get(self, request, room_id):
        """List messages in the room (GET)."""
        room = get_object_or_404(ChatRoom, id=room_id, members=request.user)
        messages = Message.objects.filter(room=room, is_deleted=False).select_related('sender').order_by('created_at')
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, room_id):
        """Create a new message (POST)."""
        room = get_object_or_404(ChatRoom, id=room_id, members=request.user)
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(room=room, sender=request.user)
        output_serializer = MessageSerializer(message, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    