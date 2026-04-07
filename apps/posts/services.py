from django.db import models
from django.db.models import Q, Count, Case, When, IntegerField, Prefetch
from django.utils import timezone
from django.conf import settings
from .models import Post, PostVisibilityRule, PostAudience


class PostVisibilityService:
    """Service for handling post visibility filtering with performance optimization."""
    
    @staticmethod
    def get_visible_posts_for_user(user, limit=20, offset=0):
        """
        Get posts visible to a user with optimized database queries.
        Uses precomputed audience table when available, falls back to real-time filtering.
        """
        # Try precomputed audience first (for performance)
        posts_from_audience = PostVisibilityService._get_posts_from_precomputed_audience(
            user, limit, offset
        )
        
        if posts_from_audience.exists():
            return posts_from_audience
        
        # Fallback to real-time filtering
        return PostVisibilityService._get_posts_realtime_filtering(user, limit, offset)
    
    @staticmethod
    def _get_posts_from_precomputed_audience(user, limit, offset):
        """Get posts from precomputed audience table."""
        from .models import PostLike, PostComment
        
        post_ids = PostAudience.objects.filter(
            user=user
        ).select_related('post').order_by('-post__created_at').values_list('post', flat=True)[
            offset:offset + limit
        ]
        
        return Post.objects.filter(
            id__in=post_ids,
            is_active=True,
            is_deleted=False
        ).select_related('author').prefetch_related(
            'media',
            Prefetch('likes', queryset=PostLike.objects.none()),  # We'll handle likes separately
            Prefetch('comments', queryset=PostComment.objects.none())  # We'll handle comments separately
        )
    
    @staticmethod
    def _get_posts_realtime_filtering(user, limit, offset):
        """Real-time filtering for posts when precomputed audience is not available."""
        from apps.relations.models import UserConnection
        from .models import PostLike, PostComment
        
        # Get user's connections
        connected_user_ids = []
        connections = UserConnection.get_user_connections(user)
        
        for connection in connections:
            if connection.user1 != user:
                connected_user_ids.append(connection.user1.id)
            if connection.user2 != user:
                connected_user_ids.append(connection.user2.id)
        
        # Get user's profile for custom visibility
        user_profile = None
        try:
            user_profile = user.profile
        except:
            pass
        
        # Build base queryset
        base_queryset = Post.objects.filter(
            is_active=True,
            is_deleted=False
        ).select_related('author', 'custom_visibility_rule').prefetch_related(
            'media',
            Prefetch('likes', queryset=PostLike.objects.none()),
            Prefetch('comments', queryset=PostComment.objects.none())
        )
        
        # Build visibility conditions
        visibility_conditions = Q()
        
        # Public posts
        visibility_conditions |= Q(visibility='public')
        
        # User's own posts
        visibility_conditions |= Q(author=user)
        
        # Connection posts
        if connected_user_ids:
            visibility_conditions |= Q(
                visibility='connections',
                author_id__in=connected_user_ids
            )
        
        # Custom visibility posts
        if user_profile:
            eligible_rule_ids = PostVisibilityService._get_eligible_rule_ids_for_user(user_profile)
            if eligible_rule_ids:
                visibility_conditions |= Q(
                    visibility='custom',
                    custom_visibility_rule_id__in=eligible_rule_ids
                )
        
        return base_queryset.filter(visibility_conditions).order_by('-created_at')[offset:offset + limit]
    
    @staticmethod
    def _get_eligible_rule_ids_for_user(user_profile):
        """Get IDs of visibility rules that user is eligible for."""
        eligible_rules = []
        
        rules = PostVisibilityRule.objects.filter(is_active=True)
        
        for rule in rules:
            if rule.is_user_eligible(user_profile.user):
                eligible_rules.append(rule.id)
        
        return eligible_rules
    
    @staticmethod
    def can_user_view_post(user, post):
        """
        Check if user can view a specific post.
        This is used for individual post access checks.
        """
        return post.get_visible_to_user(user)
    
    @staticmethod
    def precompute_audience_for_post(post):
        """
        Precompute audience for a post and store in PostAudience table.
        This should be called in background tasks for performance.
        """
        from django.contrib.auth import get_user_model
        from apps.relations.models import UserConnection
        from apps.profiles.models import UserProfile
        
        User = get_user_model()
        
        # Clear existing audience
        PostAudience.objects.filter(post=post).delete()
        
        audience_entries = []
        
        # Author can always view
        audience_entries.append(
            PostAudience(
                post=post,
                user=post.author,
                visibility_reason='author'
            )
        )
        
        # Public posts - all users
        if post.visibility == 'public':
            for user in User.objects.filter(is_active=True):
                if user != post.author:
                    audience_entries.append(
                        PostAudience(
                            post=post,
                            user=user,
                            visibility_reason='public'
                        )
                    )
        
        # Connection posts - connected users
        elif post.visibility == 'connections':
            connections = UserConnection.get_user_connections(post.author)
            
            for connection in connections:
                connected_user = connection.user2 if connection.user1 == post.author else connection.user1
                audience_entries.append(
                    PostAudience(
                        post=post,
                        user=connected_user,
                        visibility_reason='connection'
                    )
                )
        
        # Custom visibility - users matching the rule
        elif post.visibility == 'custom' and post.custom_visibility_rule:
            eligible_profiles = post.custom_visibility_rule.get_eligible_users_queryset()
            
            for profile in eligible_profiles:
                if profile.user != post.author:
                    audience_entries.append(
                        PostAudience(
                            post=post,
                            user=profile.user,
                            visibility_reason='custom_rule'
                        )
                    )
        
        # Bulk create audience entries
        if audience_entries:
            PostAudience.objects.bulk_create(audience_entries, batch_size=1000)
    
    @staticmethod
    def invalidate_post_audience(post):
        """Remove precomputed audience for a post (when visibility changes)."""
        PostAudience.objects.filter(post=post).delete()
    
    @staticmethod
    def get_feed_with_engagement_data(user, limit=20, offset=0):
        """
        Get user's feed with engagement data and user interactions.
        Optimized for mobile feed display.
        """
        posts = PostVisibilityService.get_visible_posts_for_user(user, limit, offset)
        
        # Add engagement data and user interactions
        posts_with_data = []
        
        for post in posts:
            # Get user's interaction with this post
            user_like = None
            user_save = None
            
            if hasattr(post, 'likes'):
                user_like = post.likes.filter(user=user, is_active=True).first()
            
            if hasattr(post, 'saves'):
                user_save = post.saves.filter(user=user, is_active=True).first()
            
            post_data = {
                'id': post.id,
                'author': {
                    'id': post.author.id,
                    'mobile_number': post.author.mobile_number,
                    'name': post.author.profile.firstname if hasattr(post.author, 'profile') else post.author.mobile_number
                },
                'content': post.content,
                'visibility': post.visibility,
                'created_at': post.created_at,
                'updated_at': post.updated_at,
                'engagement': {
                    'likes_count': post.likes_count,
                    'comments_count': post.comments_count,
                    'shares_count': post.shares_count
                },
                'user_interaction': {
                    'is_liked': bool(user_like),
                    'is_saved': bool(user_save)
                },
                'media': [
                    {
                        'id': media.id,
                        'file': media.file.url if media.file else None,
                        'media_type': media.media_type,
                        'caption': media.caption,
                        'thumbnail': media.thumbnail.url if media.thumbnail else None
                    }
                    for media in post.media.all()
                ],
                'media_count': post.media.count() if hasattr(post, 'media') else 0
            }
            
            posts_with_data.append(post_data)
        
        return posts_with_data


class PostEngagementService:
    """Service for handling post engagement operations."""
    
    @staticmethod
    def like_post(user, post):
        """Like or unlike a post."""
        from .models import PostLike
        
        like, created = PostLike.objects.get_or_create(
            post=post,
            user=user,
            defaults={'is_active': True}
        )
        
        if not created:
            # Toggle like status
            like.is_active = not like.is_active
            like.save()
        
        # Update post like count
        post.update_engagement_counts()
        
        return like, created
    
    @staticmethod
    def save_post(user, post):
        """Save or unsave a post."""
        from .models import PostSave
        
        save, created = PostSave.objects.get_or_create(
            post=post,
            user=user,
            defaults={'is_active': True}
        )
        
        if not created:
            # Toggle save status
            save.is_active = not save.is_active
            save.save()
        
        return save, created
    
    @staticmethod
    def share_post(user, post, share_text="", platform="internal"):
        """Share a post."""
        from .models import PostShare
        
        share = PostShare.objects.create(
            post=post,
            shared_by=user,
            share_text=share_text,
            share_platform=platform
        )
        
        # Update post share count
        post.update_engagement_counts()
        
        return share
    
    @staticmethod
    def report_post(user, post, reason, description=""):
        """Report a post."""
        from .models import PostReport
        
        report, created = PostReport.objects.get_or_create(
            post=post,
            reported_by=user,
            defaults={
                'reason': reason,
                'description': description
            }
        )
        
        if created:
            post.is_reported = True
            post.save(update_fields=['is_reported'])
        
        return report, created


class PostMediaService:
    """Service for handling post media operations."""
    
    @staticmethod
    def get_media_type_from_file(file):
        """Determine media type from file."""
        from django.core.files.images import get_image_dimensions
        
        content_type = file.content_type if hasattr(file, 'content_type') else ''
        
        if content_type.startswith('image/'):
            return 'image'
        elif content_type.startswith('video/'):
            return 'video'
        elif content_type.startswith('audio/'):
            return 'audio'
        elif content_type.startswith('application/pdf') or content_type.startswith('application/msword') or content_type.startswith('application/vnd'):
            return 'document'
        else:
            # Fallback: check file extension
            name = file.name.lower()
            if name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                return 'image'
            elif name.endswith(('.mp4', '.avi', '.mov', '.wmv')):
                return 'video'
            elif name.endswith(('.mp3', '.wav', '.flac')):
                return 'audio'
            elif name.endswith(('.pdf', '.doc', '.docx', '.txt')):
                return 'document'
        
        return 'document'  # Default fallback
    
    @staticmethod
    def create_media_attachment(post, uploaded_file, caption=""):
        """Create media attachment for a post."""
        from .models import PostMedia
        
        media_type = PostMediaService.get_media_type_from_file(uploaded_file)
        
        media = PostMedia.objects.create(
            post=post,
            file=uploaded_file,
            media_type=media_type,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            mime_type=uploaded_file.content_type if hasattr(uploaded_file, 'content_type') else 'application/octet-stream',
            caption=caption
        )
        
        # Generate thumbnail for images
        if media_type == 'image':
            PostMediaService._generate_thumbnail(media)
        
        return media
    
    @staticmethod
    def _generate_thumbnail(media):
        """Generate thumbnail for image media."""
        try:
            from PIL import Image
            from io import BytesIO
            from django.core.files.base import ContentFile
            import uuid
            import os
            
            # Open the image
            image = Image.open(media.file)
            
            # Create thumbnail (300x300 max)
            image.thumbnail((300, 300), Image.Resampling.LANCZOS)
            
            # Save thumbnail to BytesIO
            thumb_io = BytesIO()
            image_format = image.format or 'JPEG'
            image.save(thumb_io, format=image_format, quality=85)
            
            # Generate shorter filename with UUID
            file_ext = os.path.splitext(media.original_filename)[1]
            if not file_ext:
                file_ext = '.jpg'
            thumb_filename = f"thumb_{uuid.uuid4().hex[:12]}{file_ext}"
            
            # Save to model
            media.thumbnail.save(thumb_filename, ContentFile(thumb_io.getvalue()), save=True)
            
        except Exception as e:
            # Log error but don't fail the media creation
            print(f"Thumbnail generation failed: {e}")
