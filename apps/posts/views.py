from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import traceback
from django.views.decorators.cache import never_cache
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.decorators import method_decorator

from django.utils import timezone
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.paginator import Paginator
import json

from .models import Post, PostVisibilityRule, PostComment, PostLike, PostShare, PostSave, PostReport, PostMedia
from .services import PostVisibilityService, PostEngagementService, PostMediaService
from .serializers import (
    PostSerializer, PostCreateSerializer, PostUpdateSerializer,
    PostCommentSerializer, PostCommentCreateSerializer,
    PostVisibilityRuleSerializer
)
from .notification_helpers import get_users_for_post_notification
from apps.notifications.services import NotificationService, get_user_display_name

@method_decorator(never_cache, name='dispatch')
class PostCreateView(APIView):
    """Create a new post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Extract only the fields required by the serializer (avoid copying file objects)
            data = {
                'content': request.data.get('content'),
                'visibility': request.data.get('visibility'),
                'custom_visibility_rule': request.data.get('custom_visibility_rule')
            }
            
            # Handle visibility rule for custom visibility
            if data.get('visibility') == 'custom':
                rule_id = data.get('custom_visibility_rule')
                
                if not rule_id:
                    return Response(
                        {'error': 'Custom visibility requires a visibility rule ID'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    rule = PostVisibilityRule.objects.get(id=rule_id, is_active=True)
                    # Rule is valid, PrimaryKeyRelatedField will handle the ID
                except PostVisibilityRule.DoesNotExist:
                    return Response(
                        {'error': 'Invalid visibility rule'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            serializer = PostCreateSerializer(data=data)
            if serializer.is_valid():
                with transaction.atomic():
                    post = serializer.save(author=request.user)
                    
                    # Handle media uploads
                    media_files = request.FILES.getlist('media') if hasattr(request.FILES, 'getlist') else []
                    captions = request.data.getlist('media_captions') if hasattr(request.data, 'getlist') else []
                    
                    for i, media_file in enumerate(media_files):
                        caption = captions[i] if i < len(captions) else ""
                        PostMediaService.create_media_attachment(post, media_file, caption)
                    
                    # Precompute audience for performance
                    PostVisibilityService.precompute_audience_for_post(post)
                    
                    # Send post creation notifications to relevant users
                    users_to_notify = get_users_for_post_notification(post, request.user)
                    if users_to_notify:
                        NotificationService.create_post_notification(
                            post=post,
                            notification_type='post_created',
                            users=users_to_notify,
                            message=f"New post by {get_user_display_name(request.user)}: {post.content[:100]}...",
                            actor=request.user
                        )
                    
                    # Serialize and return
                    response_serializer = PostSerializer(
                        post,
                        context={'request': request}
                    )
                    
                    return Response(
                        response_serializer.data,
                        status=status.HTTP_201_CREATED
                    )
            
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            return Response({
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=500)

class PostUpdateView(APIView):
    """Update an existing post."""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id, is_active=True, is_deleted=False)
            
            # Check if user is the author
            if post.author != request.user:
                return Response(
                    {'error': 'Only the author can update this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Extract only the fields required by the serializer (avoid copying file objects)
            data = {
                'content': request.data.get('content'),
                'visibility': request.data.get('visibility'),
                'custom_visibility_rule': request.data.get('custom_visibility_rule')
            }
            
            # Handle visibility changes
            if 'visibility' in data and data['visibility'] != post.visibility:
                # Invalidate precomputed audience
                PostVisibilityService.invalidate_post_audience(post)
                
                # Handle custom visibility
                if data['visibility'] == 'custom':
                    rule_id = data.get('custom_visibility_rule')
                    if not rule_id:
                        return Response(
                            {'error': 'Custom visibility requires a visibility rule ID'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    try:
                        rule = PostVisibilityRule.objects.get(id=rule_id, is_active=True)
                        # Rule is valid, PrimaryKeyRelatedField will handle the ID
                    except PostVisibilityRule.DoesNotExist:
                        return Response(
                            {'error': 'Invalid visibility rule'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    data['custom_visibility_rule'] = None
            
            serializer = PostUpdateSerializer(post, data=data, partial=True)
            if serializer.is_valid():
                with transaction.atomic():
                    updated_post = serializer.save()
                    
                    # Recompute audience if visibility changed
                    if 'visibility' in data:
                        PostVisibilityService.precompute_audience_for_post(updated_post)
                        
                        # Send post update notifications if visibility changed
                        users_to_notify = self._get_users_for_post_notification(updated_post)
                        if users_to_notify:
                            NotificationService.create_post_notification(
                                post=updated_post,
                                notification_type='post_updated',
                                users=users_to_notify,
                                message=f"Post updated by {request.user.mobile_number}: {updated_post.content[:100]}...",
                                actor=request.user
                            )
                    
                    response_serializer = PostSerializer(
                        updated_post,
                        context={'request': request}
                    )
                    
                    return Response(response_serializer.data)
            
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostDeleteView(APIView):
    """Delete a post (soft delete)."""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id, is_active=True, is_deleted=False)
            
            # Check if user is the author
            if post.author != request.user:
                return Response(
                    {'error': 'Only the author can delete this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            with transaction.atomic():
                # Soft delete the post
                post.is_deleted = True
                post.deleted_at = timezone.now()
                post.save(update_fields=['is_deleted', 'deleted_at'])
                
                # Remove from precomputed audience
                PostVisibilityService.invalidate_post_audience(post)
                
                return Response(
                    {'message': 'Post deleted successfully'},
                    status=status.HTTP_200_OK
                )
                
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostFeedView(APIView):
    """Get user's feed with visible posts."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get pagination parameters
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 20))
            
            # Calculate offset
            offset = (page - 1) * page_size
            
            # Get visible posts
            posts_data = PostVisibilityService.get_feed_with_engagement_data(
                user=request.user,
                limit=page_size,
                offset=offset
            )
            
            # Get total count for pagination
            # Use the same method that was used to get posts
            if posts_data:
                total_posts = len(posts_data)
            else:
                total_posts = 0
            
            # Calculate pagination info
            total_pages = (total_posts + page_size - 1) // page_size
            has_next = page < total_pages
            has_previous = page > 1
            
            return Response({
                'posts': posts_data,
                'pagination': {
                    'current_page': page,
                    'total_pages': total_pages,
                    'total_posts': total_posts,
                    'page_size': page_size,
                    'has_next': has_next,
                    'has_previous': has_previous
                }
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostDetailView(APIView):
    """Get detailed information about a specific post."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to view this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get detailed post data
            serializer = PostSerializer(
                post,
                context={'request': request}
            )
            
            return Response(serializer.data)
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostLikeView(APIView):
    """Like or unlike a post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to interact with this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            like, created = PostEngagementService.like_post(request.user, post)
            
            # Send notification to post author if someone else liked their post
            if post.author != request.user and like.is_active:
                NotificationService.create_post_notification(
                    post=post,
                    notification_type='post_liked',
                    users=[post.author],
                    message=f"{get_user_display_name(request.user)} liked your post",
                    actor=request.user
                )
            
            return Response({
                'is_liked': like.is_active,
                'likes_count': post.likes_count,
                'action': 'liked' if (created and like.is_active) else 'unliked'
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostCommentListView(APIView):
    """List comments for a post."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to view this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get comments with pagination
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 20))
            
            comments = PostComment.objects.filter(
                post=post,
                is_deleted=False,
                parent=None  # Only top-level comments
            ).select_related('author').prefetch_related('replies').order_by('-created_at')
            
            paginator = Paginator(comments, page_size)
            page_obj = paginator.get_page(page)
            
            serializer = PostCommentSerializer(
                page_obj.object_list,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'comments': serializer.data,
                'pagination': {
                    'current_page': page,
                    'total_pages': paginator.num_pages,
                    'total_comments': paginator.count,
                    'page_size': page_size,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostCommentCreateView(APIView):
    """Create a comment on a post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to interact with this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            data = request.data.copy()
            data['post'] = post.id
            data['author'] = request.user.id
            
            # Handle reply comments
            parent_id = data.get('parent_id')
            if parent_id:
                try:
                    parent_comment = PostComment.objects.get(
                        id=parent_id,
                        post=post,
                        is_deleted=False
                    )
                    data['parent'] = parent_comment.id
                except PostComment.DoesNotExist:
                    return Response(
                        {'error': 'Parent comment not found'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            serializer = PostCommentCreateSerializer(data=data)
            if serializer.is_valid():
                with transaction.atomic():
                    comment = serializer.save(author=request.user, post=post)
                    
                    # Update post comment count
                    post.update_engagement_counts()
                    
                    # Send notification to post author if someone else commented
                    if post.author != request.user:
                        NotificationService.create_post_notification(
                            post=post,
                            notification_type='post_commented',
                            users=[post.author],
                            message=f"{get_user_display_name(request.user)} commented on your post",
                            actor=request.user
                        )
                    
                    # Send notification to parent comment author if this is a reply
                    if comment.parent and comment.parent.author != request.user:
                        NotificationService.create_post_notification(
                            post=post,
                            notification_type='post_commented',
                            users=[comment.parent.author],
                            message=f"{get_user_display_name(request.user)} replied to your comment",
                            actor=request.user
                        )
                    
                    response_serializer = PostCommentSerializer(
                        comment,
                        context={'request': request}
                    )
                    
                    return Response(
                        response_serializer.data,
                        status=status.HTTP_201_CREATED
                    )
            
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostShareView(APIView):
    """Share a post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to share this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            share_text = request.data.get('share_text', '')
            platform = request.data.get('platform', 'internal')
            
            share = PostEngagementService.share_post(
                user=request.user,
                post=post,
                share_text=share_text,
                platform=platform
            )
            
            # Send notification to post author if someone else shared their post
            if post.author != request.user:
                NotificationService.create_post_notification(
                    post=post,
                    notification_type='post_shared',
                    users=[post.author],
                    message=f"{get_user_display_name(request.user)} shared your post",
                    actor=request.user
                )
            
            return Response({
                'message': 'Post shared successfully',
                'share_id': share.id,
                'shares_count': post.shares_count
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostSaveView(APIView):
    """Save or unsave a post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to save this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            save, created = PostEngagementService.save_post(request.user, post)
            
            return Response({
                'is_saved': save.is_active,
                'action': 'saved' if (created and save.is_active) else 'unsaved'
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostReportView(APIView):
    """Report a post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check visibility
            if not PostVisibilityService.can_user_view_post(request.user, post):
                return Response(
                    {'error': 'You do not have permission to report this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            reason = request.data.get('reason')
            description = request.data.get('description', '')
            
            if not reason:
                return Response(
                    {'error': 'Reason is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate reason
            valid_reasons = [choice[0] for choice in PostReport.REPORT_REASONS]
            if reason not in valid_reasons:
                return Response(
                    {'error': 'Invalid reason'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            report, created = PostEngagementService.report_post(
                user=request.user,
                post=post,
                reason=reason,
                description=description
            )
            
            return Response({
                'message': 'Post reported successfully' if created else 'Post already reported',
                'report_id': report.id
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PostMediaUploadView(APIView):
    """Add media to an existing post."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        try:
            post = Post.objects.get(
                id=post_id,
                is_active=True,
                is_deleted=False
            )
            
            # Check if user is the author
            if post.author != request.user:
                return Response(
                    {'error': 'Only the author can add media to this post'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            media_files = request.FILES.getlist('media') if hasattr(request.FILES, 'getlist') else []
            captions = request.data.getlist('media_captions') if hasattr(request.data, 'getlist') else []
            
            if not media_files:
                return Response(
                    {'error': 'No media files provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            created_media = []
            
            with transaction.atomic():
                for i, media_file in enumerate(media_files):
                    caption = captions[i] if i < len(captions) else ""
                    media = PostMediaService.create_media_attachment(post, media_file, caption)
                    created_media.append(media)
            
            # Return media details
            media_data = []
            for media in created_media:
                media_data.append({
                    'id': media.id,
                    'media_type': media.media_type,
                    'original_filename': media.original_filename,
                    'file_size': media.file_size,
                    'caption': media.caption,
                    'file_url': media.file.url if media.file else None,
                    'thumbnail_url': media.thumbnail.url if media.thumbnail else None
                })
            
            return Response({
                'message': f'Successfully uploaded {len(created_media)} media files',
                'media': media_data
            })
            
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )     