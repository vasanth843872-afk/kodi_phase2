from rest_framework import serializers
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Post, PostVisibilityRule, PostComment, PostLike, 
    PostShare, PostSave, PostReport, PostMedia
)


class PostMediaSerializer(serializers.ModelSerializer):
    """Serializer for post media attachments."""
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PostMedia
        fields = [
            'id', 'media_type', 'file_url', 'thumbnail_url',
            'original_filename', 'file_size', 'caption', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class PostAuthorSerializer(serializers.ModelSerializer):
    """Serializer for post author information."""
    name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    
    class Meta:
        from django.contrib.auth import get_user_model
        model = get_user_model()
        fields = ['id', 'mobile_number', 'name', 'profile_image']
    
    def get_name(self, obj):
        """Get user's display name from profile."""
        try:
            profile = obj.profile
            names = [profile.firstname, profile.secondname, profile.thirdname]
            return ' '.join(filter(None, names)) or obj.mobile_number
        except Exception as e:
            return obj.mobile_number
    
    def get_profile_image(self, obj):
        """Get user's profile image."""
        try:
            profile = obj.profile
            if profile.image:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(profile.image.url)
                return profile.image.url
        except:
            pass
        return None


class PostSerializer(serializers.ModelSerializer):
    """Serializer for post data with full details."""
    author = PostAuthorSerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    custom_visibility_rule = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'visibility', 'custom_visibility_rule',
            'likes_count', 'comments_count', 'shares_count',
            'is_active', 'is_reported', 'created_at', 'updated_at',
            'media', 'is_liked', 'is_saved'
        ]
        read_only_fields = [
            'id', 'author', 'likes_count', 'comments_count', 'shares_count',
            'is_active', 'is_reported', 'created_at', 'updated_at'
        ]
    
    def get_is_liked(self, obj):
        """Check if current user liked this post."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.likes.filter(user=request.user, is_active=True).exists()
            except Exception as e:
                pass
        return False
    
    def get_is_saved(self, obj):
        """Check if current user saved this post."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.saves.filter(user=request.user, is_active=True).exists()
            except:
                pass
        return False
    
    def get_custom_visibility_rule(self, obj):
        """Get custom visibility rule details."""
        if obj.custom_visibility_rule:
            return PostVisibilityRuleSerializer(obj.custom_visibility_rule).data
        return None


class PostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating posts."""
    custom_visibility_rule = serializers.PrimaryKeyRelatedField(
        queryset=PostVisibilityRule.objects.filter(is_active=True),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Post
        fields = ['content', 'visibility', 'custom_visibility_rule']
    
    def validate_content(self, value):
        """Validate post content."""
        if not value or not value.strip():
            raise serializers.ValidationError("Post content cannot be empty.")
        
        if len(value.strip()) > 5000:
            raise serializers.ValidationError("Post content cannot exceed 5000 characters.")
        
        return value.strip()
    
    def validate_visibility(self, value):
        """Validate visibility type."""
        valid_types = [choice[0] for choice in Post.VISIBILITY_TYPES]
        if value not in valid_types:
            raise serializers.ValidationError("Invalid visibility type.")
        return value
    
    def validate(self, data):
        """Validate custom visibility requirements."""
        if data.get('visibility') == 'custom' and not data.get('custom_visibility_rule'):
            raise serializers.ValidationError({
                'custom_visibility_rule': 'Custom visibility requires a visibility rule ID.'
            })
        return data


class PostUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating posts."""
    custom_visibility_rule = serializers.PrimaryKeyRelatedField(
        queryset=PostVisibilityRule.objects.filter(is_active=True),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Post
        fields = ['content', 'visibility', 'custom_visibility_rule']
    
    def validate_content(self, value):
        """Validate post content for updates."""
        if value is not None:
            if not value or not value.strip():
                raise serializers.ValidationError("Post content cannot be empty.")
            
            if len(value.strip()) > 5000:
                raise serializers.ValidationError("Post content cannot exceed 5000 characters.")
            
            return value.strip()
        return value
    
    def validate_visibility(self, value):
        """Validate visibility type for updates."""
        if value is not None:
            valid_types = [choice[0] for choice in Post.VISIBILITY_TYPES]
            if value not in valid_types:
                raise serializers.ValidationError("Invalid visibility type.")
        return value


class PostVisibilityRuleSerializer(serializers.ModelSerializer):
    """Serializer for post visibility rules."""
    created_by = PostAuthorSerializer(read_only=True)
    eligible_users_count = serializers.SerializerMethodField()
    
    class Meta:
        model = PostVisibilityRule
        fields = [
            'id', 'name', 'description', 'caste_criteria', 'religion_criteria',
            'family_name_criteria', 'area_criteria', 'is_active',
            'created_by', 'created_at', 'updated_at', 'eligible_users_count'
        ]
        read_only_fields = [
            'id', 'created_by', 'created_at', 'updated_at', 'eligible_users_count'
        ]
    
    def get_eligible_users_count(self, obj):
        """Get count of eligible users for this rule."""
        try:
            return obj.get_eligible_users_queryset().count()
        except:
            return 0
    
    def validate(self, data):
        """Validate that at least one criterion is specified."""
        criteria_fields = ['caste_criteria', 'religion_criteria', 'family_name_criteria', 'area_criteria']
        has_criteria = any(
            data.get(field) or getattr(self.instance, field, None) 
            for field in criteria_fields
        )
        
        if not has_criteria:
            raise serializers.ValidationError(
                "At least one criterion (caste, religion, family_name, or area) must be specified."
            )
        
        return data


class PostCommentSerializer(serializers.ModelSerializer):
    """Serializer for post comments."""
    author = PostAuthorSerializer(read_only=True)
    replies_count = serializers.SerializerMethodField()
    is_edited = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = PostComment
        fields = [
            'id', 'post', 'author', 'content', 'parent',
            'is_edited', 'created_at', 'updated_at', 'replies_count'
        ]
        read_only_fields = [
            'id', 'author', 'is_edited', 'created_at', 'updated_at'
        ]
    
    def get_replies_count(self, obj):
        """Get count of active replies."""
        try:
            return obj.replies.filter(is_deleted=False).count()
        except:
            return 0


class PostCommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating comments."""
    parent_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = PostComment
        fields = ['content', 'parent_id']
    
    def validate_content(self, value):
        """Validate comment content."""
        if not value or not value.strip():
            raise serializers.ValidationError("Comment content cannot be empty.")
        
        if len(value.strip()) > 1000:
            raise serializers.ValidationError("Comment content cannot exceed 1000 characters.")
        
        return value.strip()


class PostLikeSerializer(serializers.ModelSerializer):
    """Serializer for post likes."""
    user = PostAuthorSerializer(read_only=True)
    
    class Meta:
        model = PostLike
        fields = ['id', 'user', 'is_active', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class PostShareSerializer(serializers.ModelSerializer):
    """Serializer for post shares."""
    shared_by = PostAuthorSerializer(read_only=True)
    
    class Meta:
        model = PostShare
        fields = [
            'id', 'post', 'shared_by', 'share_text', 'share_platform',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'shared_by', 'is_active', 'created_at']


class PostSaveSerializer(serializers.ModelSerializer):
    """Serializer for post saves."""
    user = PostAuthorSerializer(read_only=True)
    
    class Meta:
        model = PostSave
        fields = ['id', 'post', 'user', 'is_active', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class PostReportSerializer(serializers.ModelSerializer):
    """Serializer for post reports."""
    reported_by = PostAuthorSerializer(read_only=True)
    reviewed_by = PostAuthorSerializer(read_only=True)
    
    class Meta:
        model = PostReport
        fields = [
            'id', 'post', 'reported_by', 'reason', 'description',
            'is_reviewed', 'is_action_taken', 'admin_notes',
            'reviewed_by', 'reviewed_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'reported_by', 'is_reviewed', 'is_action_taken',
            'admin_notes', 'reviewed_by', 'reviewed_at', 'created_at'
        ]


class PostListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for post lists/feeds."""
    author = PostAuthorSerializer(read_only=True)
    media_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'visibility', 'created_at',
            'likes_count', 'comments_count', 'shares_count',
            'media_count', 'is_liked', 'is_saved'
        ]
    
    def get_media_count(self, obj):
        """Get count of media attachments."""
        try:
            return obj.media.count()
        except:
            return 0
    
    def get_is_liked(self, obj):
        """Check if current user liked this post."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.likes.filter(user=request.user, is_active=True).exists()
            except:
                pass
        return False
    
    def get_is_saved(self, obj):
        """Check if current user saved this post."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.saves.filter(user=request.user, is_active=True).exists()
            except:
                pass
        return False


# Feed Serializer for optimized response
class PostFeedSerializer(serializers.Serializer):
    """Serializer for post feed responses with pagination."""
    posts = PostListSerializer(many=True, read_only=True)
    pagination = serializers.DictField(read_only=True)
    
    class Meta:
        fields = ['posts', 'pagination']


# Admin serializers
class PostAdminSerializer(serializers.ModelSerializer):
    """Serializer for admin post management."""
    author = PostAuthorSerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    reports_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'visibility', 'custom_visibility_rule',
            'likes_count', 'comments_count', 'shares_count',
            'is_active', 'is_deleted', 'is_reported', 'created_at', 'updated_at',
            'media', 'reports_count'
        ]
    
    def get_reports_count(self, obj):
        """Get count of reports for this post."""
        try:
            return obj.reports.count()
        except:
            return 0


class PostVisibilityRuleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating visibility rules (admin only)."""
    
    class Meta:
        model = PostVisibilityRule
        fields = [
            'name', 'description', 'caste_criteria', 'religion_criteria',
            'family_name_criteria', 'area_criteria', 'is_active'
        ]
    
    def validate(self, data):
        """Validate that at least one criterion is specified."""
        criteria_fields = ['caste_criteria', 'religion_criteria', 'family_name_criteria', 'area_criteria']
        has_criteria = any(data.get(field) for field in criteria_fields)
        
        if not has_criteria:
            raise serializers.ValidationError(
                "At least one criterion (caste, religion, family_name, or area) must be specified."
            )
        
        return data


# admin serializer

class PostAdminDetailSerializer(serializers.ModelSerializer):
    """Detailed admin serializer for a single post."""
    author_mobile = serializers.CharField(source='author.mobile_number', read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    reports_count = serializers.IntegerField(source='reports.count', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'author_mobile', 'content', 'visibility',
            'custom_visibility_rule', 'likes_count', 'comments_count',
            'shares_count', 'is_active', 'is_deleted', 'is_reported',
            'created_at', 'updated_at', 'media', 'reports_count'
        ]
        read_only_fields = fields


class PostAdminListSerializer(serializers.ModelSerializer):
    """Lightweight admin serializer for list views."""
    author_mobile = serializers.CharField(source='author.mobile_number', read_only=True)
    reports_count = serializers.IntegerField(source='reports.count', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'author_mobile', 'content_preview', 'visibility',
            'likes_count', 'comments_count', 'is_active', 'is_deleted',
            'is_reported', 'created_at', 'reports_count'
        ]

    content_preview = serializers.SerializerMethodField()

    def get_content_preview(self, obj):
        return obj.content[:100] if obj.content else ""


class PostCommentAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for comments."""
    author_mobile = serializers.CharField(source='author.mobile_number', read_only=True)
    post_id = serializers.IntegerField(source='post.id', read_only=True)

    class Meta:
        model = PostComment
        fields = [
            'id', 'post_id', 'author_mobile', 'content', 'parent',
            'is_edited', 'is_deleted', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class PostReportAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for reports."""
    reported_by_mobile = serializers.CharField(source='reported_by.mobile_number', read_only=True)
    post_author_mobile = serializers.CharField(source='post.author.mobile_number', read_only=True)
    post_content_preview = serializers.SerializerMethodField()

    class Meta:
        model = PostReport
        fields = [
            'id', 'post', 'post_content_preview', 'post_author_mobile',
            'reported_by_mobile', 'reason', 'description', 'is_reviewed',
            'is_action_taken', 'admin_notes', 'reviewed_by', 'reviewed_at',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_post_content_preview(self, obj):
        return obj.post.content[:100] if obj.post.content else ""


class PostVisibilityRuleAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for visibility rules (full CRUD)."""
    created_by_mobile = serializers.CharField(source='created_by.mobile_number', read_only=True)
    eligible_users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PostVisibilityRule
        fields = [
            'id', 'name', 'description', 'caste_criteria', 'religion_criteria',
            'family_name_criteria', 'area_criteria', 'is_active',
            'created_by_mobile', 'eligible_users_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by_mobile', 'eligible_users_count', 'created_at', 'updated_at']


class PostVisibilityRuleCreateUpdateSerializer(serializers.ModelSerializer):
    """For creating/updating visibility rules (admin only)."""
    class Meta:
        model = PostVisibilityRule
        fields = [
            'name', 'description', 'caste_criteria', 'religion_criteria',
            'family_name_criteria', 'area_criteria', 'is_active'
        ]

    def validate(self, data):
        criteria_fields = ['caste_criteria', 'religion_criteria', 'family_name_criteria', 'area_criteria']
        if not any(data.get(field) for field in criteria_fields):
            raise serializers.ValidationError(
                "At least one criterion (caste, religion, family_name, or area) must be specified."
            )
        return data