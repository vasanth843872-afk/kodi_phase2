from rest_framework import serializers
from django.utils import timezone
from .models import (
    Event, EventType, VisibilityLevel, RSVP, 
    EventMedia, EventComment, EventFlag, EventConfig
)
from apps.accounts.serializers import UserBasicSerializer
from apps.genealogy.serializers import PersonBasicSerializer

# ==================== EVENT TYPE SERIALIZERS ====================

class EventTypeSerializer(serializers.ModelSerializer):
    """Simple event type serializer"""
    created_by_name = serializers.CharField(source='created_by.firstname', read_only=True)
    
    class Meta:
        model = EventType
        fields = [
            'id', 'title', 'created_by', 'created_by_name',
            'family', 'is_public', 'usage_count', 'created_at'
        ]
        read_only_fields = ['created_by', 'usage_count', 'created_at']


class EventTypeCreateSerializer(serializers.ModelSerializer):
    """For creating event types"""
    class Meta:
        model = EventType
        fields = ['title', 'family', 'is_public']
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


# ==================== VISIBILITY SERIALIZERS ====================

class VisibilityLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisibilityLevel
        fields = ['id', 'code', 'name', 'description', 'is_enabled']


# ==================== EVENT SERIALIZERS ====================

class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for event listings"""
    event_type_title = serializers.CharField(source='event_type.title', read_only=True)
    created_by_name = serializers.SerializerMethodField() 
    cover_image_url = serializers.SerializerMethodField()
    user_rsvp = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    visibility_name = serializers.CharField(source='visibility.name', read_only=True)
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'event_type', 'event_type_title','description',
            'start_date', 'end_date', 'is_all_day',
            'location_name', 'city', 'is_virtual',
            'cover_image_url', 'created_by', 'created_by_name',
            'visibility', 'visibility_name', 'status',
            'rsvp_going', 'rsvp_maybe', 'rsvp_not_going',
            'view_count', 'user_rsvp', 'created_at','comment_count'
        ]
    
    def get_cover_image_url(self, obj):
        if obj.cover_image:
            return obj.cover_image.url
        return None
    
    def get_created_by_name(self, obj):
        """Get name from profile's firstname"""
        if obj.created_by:
            # Try to get from profile first (if you have a profile model)
            if hasattr(obj.created_by, 'profile') and obj.created_by.profile:
                return obj.created_by.profile.firstname or obj.created_by.username
            # Fallback to user's first_name
            return obj.created_by.firstname or obj.created_by.username
        return None
    
    def get_user_rsvp(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                rsvp = obj.rsvps.get(user=request.user)
                return {
                    'response': rsvp.response,
                    'guests_count': rsvp.guests_count
                }
            except:
                pass
        return None
    
    def get_comment_count(self, obj):
        """Get count of approved comments for this event"""
        return obj.comments.filter(is_approved=True).count()


class EventDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single event"""
    event_type = EventTypeSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    visibility = VisibilityLevelSerializer(read_only=True)
    honorees = PersonBasicSerializer(many=True, read_only=True)
    rsvp_summary = serializers.SerializerMethodField()
    media_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()
    user_can_rsvp = serializers.SerializerMethodField()
    
    class Meta:
        model = Event
        fields = '__all__'
    
    def get_rsvp_summary(self, obj):
        return {
            'going': obj.rsvp_going,
            'maybe': obj.rsvp_maybe,
            'not_going': obj.rsvp_not_going,
            'total': obj.rsvp_going + obj.rsvp_maybe + obj.rsvp_not_going
        }
    
    def get_media_count(self, obj):
        return obj.media.count()
    
    def get_comment_count(self, obj):
        return obj.comments.filter(is_approved=True).count()
    
    def get_user_can_edit(self, obj):
        request = self.context.get('request')
        if request:
            return request.user.is_staff or obj.created_by == request.user
        return False
    
    def get_user_can_rsvp(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.start_date > timezone.now()
        return False


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    """For creating/updating events"""
    event_type_title = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Event
        exclude = ['created_by', 'view_count', 'rsvp_going', 'rsvp_maybe', 'rsvp_not_going']
        read_only_fields = ['status', 'created_at', 'updated_at']
    
    def validate_visibility(self, value):
        """Enforce max visibility from admin config"""
        request = self.context.get('request')
        config = EventConfig.get_config()
        
        if request and not request.user.is_staff:
            max_level = config.max_allowed_visibility
            
            # Check if selected level exceeds max
            if self._is_more_restrictive(value.code, max_level):
                raise serializers.ValidationError(
                    f"Cannot use '{value.name}'. Maximum allowed is {max_level}"
                )
        
        return value
    
    def _is_more_restrictive(self, level_code, max_level_code):
        """Check if level is more restrictive than max"""
        hierarchy = ['PUBLIC', 'CONNECTED', 'FAMILY', 'CASTE', 'RELIGION', 'LOCATION', 'PRIVATE']
        try:
            level_index = hierarchy.index(level_code)
            max_index = hierarchy.index(max_level_code)
            return level_index > max_index
        except ValueError:
            return False
    
    def validate(self, data):
        """Validate event dates"""
        if data.get('end_date') and data.get('start_date'):
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError({
                    'end_date': 'End date cannot be before start date'
                })
        return data
    
    def create(self, validated_data):
        # Handle event type
        event_type_title = validated_data.pop('event_type_title', None)
        if event_type_title:
            # Find or create event type
            event_type, created = EventType.objects.get_or_create(
                title__iexact=event_type_title,
                created_by=self.context['request'].user,
                defaults={
                    'title': event_type_title,
                    'created_by': self.context['request'].user
                }
            )
            validated_data['event_type'] = event_type
        
        # ✅ FIX: Set default visibility to CONNECTED if not provided
        if 'visibility' not in validated_data:
            try:
                # Get CONNECTED visibility level
                connected_visibility = VisibilityLevel.objects.get(code='CONNECTED')
                validated_data['visibility'] = connected_visibility
            except VisibilityLevel.DoesNotExist:
                # If CONNECTED doesn't exist, get the default
                connected_visibility = VisibilityLevel.objects.filter(is_enabled=True).first()
                validated_data['visibility'] = connected_visibility
        
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)
    
# ==================== RSVP SERIALIZERS ====================

class RSVPSerializer(serializers.ModelSerializer):
    # Add these fields for user details
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_first_name = serializers.SerializerMethodField()
    user_last_name = serializers.SerializerMethodField()
    user_full_name = serializers.SerializerMethodField()
    user_profile_image = serializers.SerializerMethodField()
    
    class Meta:
        model = RSVP
        fields = [
            'id', 'response', 'guests_count', 'guest_names',
            'dietary_restrictions', 'notes', 'created_at',
            'user', 'user_name', 'user_first_name', 'user_last_name', 
            'user_full_name', 'user_profile_image'
        ]
        read_only_fields = ['user', 'created_at']
    
    def get_user_first_name(self, obj):
        """Get first name from UserProfile"""
        if obj.user and hasattr(obj.user, 'profile'):
            return obj.user.profile.firstname
        return obj.user.username if obj.user else None
    
    def get_user_last_name(self, obj):
        """Get second/third name from profile (combined as last name)"""
        if obj.user and hasattr(obj.user, 'profile'):
            profile = obj.user.profile
            # Combine secondname and thirdname for last name
            last_parts = []
            if profile.secondname:
                last_parts.append(profile.secondname)
            if profile.thirdname:
                last_parts.append(profile.thirdname)
            return ' '.join(last_parts) if last_parts else ''
        return ''
    
    def get_user_full_name(self, obj):
        """Get full name from profile (firstname + secondname + thirdname)"""
        if obj.user and hasattr(obj.user, 'profile'):
            profile = obj.user.profile
            name_parts = []
            if profile.firstname:
                name_parts.append(profile.firstname)
            if profile.secondname:
                name_parts.append(profile.secondname)
            if profile.thirdname:
                name_parts.append(profile.thirdname)
            return ' '.join(name_parts) if name_parts else obj.user.username
        return obj.user.username if obj.user else None
    
    def get_user_profile_image(self, obj):
        """Get profile image URL"""
        if obj.user and hasattr(obj.user, 'profile') and obj.user.profile.image:
            return obj.user.profile.image.url
        return None
    
    def validate(self, data):
        """Check if event is in future"""
        event = self.context['event']
        if event.start_date < timezone.now():
            raise serializers.ValidationError("Cannot RSVP to past events")
        return data
    
    def create(self, validated_data):
        validated_data['event'] = self.context['event']
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ==================== MEDIA SERIALIZERS ====================

class EventMediaSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)
    
    class Meta:
        model = EventMedia
        fields = [
            'id', 'media_type', 'file', 'thumbnail',
            'caption', 'uploaded_by', 'uploaded_by_name',
            'tagged_persons', 'uploaded_at'
        ]
        read_only_fields = ['uploaded_by', 'uploaded_at']


# ==================== COMMENT SERIALIZERS ====================

class EventCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    replies = serializers.SerializerMethodField()
    
    class Meta:
        model = EventComment
        fields = [
            'id', 'content', 'user', 'user_name',
            'parent', 'replies', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']
    
    def get_replies(self, obj):
        if obj.parent is None:
            replies = obj.replies.filter(is_approved=True)
            return EventCommentSerializer(replies, many=True).data
        return []
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['event'] = self.context['event']
        return super().create(validated_data)


# ==================== FLAG SERIALIZERS ====================

class EventFlagSerializer(serializers.ModelSerializer):
    reported_by_name = serializers.CharField(source='reported_by.username', read_only=True)
    
    class Meta:
        model = EventFlag
        fields = [
            'id', 'reason', 'description', 'status',
            'reported_by', 'reported_by_name', 'created_at'
        ]
        read_only_fields = ['reported_by', 'status', 'created_at']


# ==================== ADMIN CONFIG SERIALIZER ====================

class EventConfigSerializer(serializers.ModelSerializer):
    default_visibility_code = serializers.CharField(source='default_visibility.code', read_only=True)
    default_visibility_name = serializers.CharField(source='default_visibility.name', read_only=True)
    
    class Meta:
        model = EventConfig
        exclude = ['id', 'updated_by']
        read_only_fields = ['updated_at']