from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import *
from .utils import _get_profile_name,_get_profile_image

User = get_user_model()


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "mobile_number"]
        
class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ['id', 'filename', 'file_size', 'content_type', 'file_url', 'created_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class MessageSerializer(serializers.ModelSerializer):
    sender_mobile = serializers.CharField(source="sender.mobile_number", read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "content", "sender_id", "sender_mobile", "created_at", "is_deleted",'attachments']
        read_only_fields = ["id", "sender_id", "sender_mobile", "created_at", "is_deleted"]
        
class MessageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['content']  # only content can be changed


class ChatRoomSerializer(serializers.ModelSerializer):
    members = MemberSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ["id", "room_type", "name", "members", "last_message", "unread_count", "created_at"]

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).order_by("-created_at").first()
        if msg:
            return {
                "content": msg.content,
                "sender_mobile": msg.sender.mobile_number if msg.sender else None,
                "created_at": msg.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        user = request.user
        # Messages in this room that don't have a read status for this user
        read_ids = obj.messages.filter(read_statuses__user=user).values_list("id", flat=True)
        return obj.messages.filter(is_deleted=False).exclude(
            id__in=read_ids
        ).exclude(sender=user).count()


class CreateDirectRoomSerializer(serializers.Serializer):
    """POST /api/chat/rooms/direct/ — start or retrieve a DM with another user."""
    target_user_id = serializers.IntegerField()

    def validate_target_user_id(self, value):
        request = self.context["request"]
        if value == request.user.id:
            raise serializers.ValidationError("You cannot chat with yourself.")
        try:
            User.objects.get(id=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        return value


class CreateGroupRoomSerializer(serializers.Serializer):
    """POST /api/chat/rooms/group/ — create a group room."""
    name = serializers.CharField(max_length=255)
    member_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    
    
class BlockUserSerializer(serializers.Serializer):
    """POST /api/accounts/block/ — block a user."""
    user_id = serializers.IntegerField()
 
    def validate_user_id(self, value):
        request = self.context['request']
        if value == request.user.id:
            raise serializers.ValidationError("You cannot block yourself.")
        if not User.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("User not found.")
        return value
 
 
class BlockedUserSerializer(serializers.ModelSerializer):
    """Serializes a blocked user entry for the blocked list."""
    blocked_id = serializers.IntegerField(source='blocked.id', read_only=True)
    blocked_mobile = serializers.CharField(source='blocked.mobile_number', read_only=True)
 
    class Meta:
        model = BlockedUser
        fields = ['id', 'blocked_id', 'blocked_mobile', 'created_at']
        
class ContactNicknameSerializer(serializers.Serializer):
    contact_id = serializers.IntegerField()
    nickname = serializers.CharField(max_length=100)
 
    def validate_contact_id(self, value):
        if not User.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("User not found.")
        return value
    
# returns all mebers of the group
class GroupMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id')
    mobile_number = serializers.CharField(source='user.mobile_number')
    profile_name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoomMember
        fields = ['user_id', 'mobile_number', 'role', 'joined_at', 'is_muted', 'profile_name', 'profile_image']

    def get_profile_name(self, obj):
        return _get_profile_name(obj.user)  # use your helper

    def get_profile_image(self, obj):
        request = self.context.get('request')
        return _get_profile_image(obj.user, request)
    



# class MessageSerializer(serializers.ModelSerializer):
#     sender = UserMinimalSerializer(read_only=True)   # assuming you have such a serializer
#     attachments = MessageAttachmentSerializer(many=True, read_only=True)

#     class Meta:
#         model = Message
#         fields = [
#             'id', 'room', 'sender', 'content', 'created_at',
#             'is_edited', 'edited_at', 'is_deleted', 'attachments'
#         ]
#         read_only_fields = fields


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True)
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True
    )

    def validate(self, data):
        content = data.get('content', '').strip()
        attachments = data.get('attachments', [])
        if not content and not attachments:
            raise serializers.ValidationError(
                "Either content or at least one attachment is required."
            )
        # Optional: enforce file size/type limits
        max_size = 10 * 1024 * 1024  # 10 MB per file
        allowed_types = ['image/jpeg', 'image/png', 'application/pdf', 'text/plain']
        for file in attachments:
            if file.size > max_size:
                raise serializers.ValidationError(
                    f"File {file.name} exceeds {max_size // (1024*1024)} MB."
                )
            if file.content_type not in allowed_types:
                raise serializers.ValidationError(
                    f"File type {file.content_type} not allowed."
                )
        return data

    def save(self, room, sender):
        content = self.validated_data.get('content', '')
        attachments = self.validated_data.get('attachments', [])
        message = Message.objects.create(
            room=room,
            sender=sender,
            content=content
        )
        for file in attachments:
            MessageAttachment.objects.create(
                message=message,
                file=file,
                filename=file.name,
                file_size=file.size,
                content_type=file.content_type
            )
        return message
    
    # admin serializer
# serializers.py
from apps.profiles.models import UserProfile  
class UserAdminSerializer(serializers.ModelSerializer):
    # Use the correct related_name from UserProfile → User
    # If your OneToOneField uses related_name='userprofile', keep 'userprofile'
    # If it uses related_name='profile', change to 'profile'
        # last_name = serializers.CharField(source='userprofile.lastname', read_only=True, default='')
    # email = serializers.EmailField(source='userprofile.email', read_only=True, default='')
    # profile_image = serializers.SerializerMethodField()
    
    first_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'mobile_number', 'first_name',
            'is_active', 'is_staff', 'created_at', 'last_login', 
        ]
        read_only_fields = ['id', 'created_at', 'last_login']

    
    def get_first_name(self, obj):
        if hasattr(obj, 'profile') and obj.profile:
            return obj.profile.firstname
        return ""

    def get_profile_image(self, obj):
        request = self.context.get('request')
        return _get_profile_image(obj, request)   # reuse your existing helper