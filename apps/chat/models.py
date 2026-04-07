from django.db import models
from django.conf import settings
from django.utils import timezone


class ChatRoom(models.Model):
    """
    A room can be:
      - direct: between two users (room_type='direct')
      - group:  family or event chat (room_type='group')
    """
    ROOM_TYPE_CHOICES = [
        ('direct', 'Direct'),
        ('group', 'Group'),
    ]

    room_type = models.CharField(max_length=10, choices=ROOM_TYPE_CHOICES, default='direct')
    name = models.CharField(max_length=255, blank=True, null=True)  # used for group rooms
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chat_rooms',
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_rooms'

    def __str__(self):
        if self.room_type == 'direct':
            members = self.members.all()
            if members.count() == 2:
                return f"DM: {members[0].mobile_number} ↔ {members[1].mobile_number}"
        return self.name or f"Room #{self.pk}"

    @classmethod
    def get_or_create_direct_room(cls, user1, user2):
        """Find existing DM room or create one."""
        # Look for a direct room that has exactly these two members
        rooms = cls.objects.filter(room_type='direct', members=user1).filter(members=user2)
        for room in rooms:
            if room.members.count() == 2:
                return room, False
        room = cls.objects.create(room_type='direct')
        room.members.add(user1, user2)
        return room, True


class Message(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True) 
    edited_at = models.DateTimeField(null=True, blank=True)
    is_edited = models.BooleanField(default=False)
    
    @property
    def has_attachments(self):
        return self.attachments.exists()

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.room}] {self.sender}: {self.content[:40]}"


class MessageReadStatus(models.Model):
    """Tracks which messages each user has read."""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message_read_status'
        unique_together = ('message', 'user')
        
        
class BlockedUser(models.Model):
    """
    Tracks which users have blocked which other users.
 
    blocker  → the user who initiated the block
    blocked  → the user who got blocked
    """
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocking',       # blocker.blocking.all() → who they blocked
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocked_by',     # blocked.blocked_by.all() → who blocked them
    )
    created_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'blocked_users'
        unique_together = ('blocker', 'blocked')   # can't block same person twice
 
    def __str__(self):
        return f"{self.blocker.mobile_number} blocked {self.blocked.mobile_number}"
    
class ContactNickname(models.Model):
    """User can give a custom name/label to another user's number."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_nicknames')
    contact = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nicknamed_by')
    nickname = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'chat_contact_nicknames'
        unique_together = ('owner', 'contact')
 
    def __str__(self):
        return f"{self.owner.mobile_number} calls {self.contact.mobile_number} '{self.nickname}'"
    
class ChatRoomMember(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]
    
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    # Per-user clear: messages before this timestamp are hidden for this user
    cleared_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_muted = models.BooleanField(default=False)
 
    class Meta:
        db_table = 'chat_room_members'
        unique_together = ('room', 'user')
        
        
        

# file attach
class MessageAttachment(models.Model):
    """File attachment for a message."""
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to='chat_attachments/%Y/%m/%d/',
        max_length=500
    )
    filename = models.CharField(max_length=255)          # original name
    file_size = models.PositiveIntegerField()            # in bytes
    content_type = models.CharField(max_length=100)      # MIME type (e.g., image/png)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message_attachments'
        ordering = ['created_at']

    def __str__(self):
        return f"Attachment {self.filename} (msg {self.message_id})"