from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from .models import UserProfile
from .serializers import (
    PublicProfileSerializer,
    PrivateProfileSerializer,
    ProfileUpdateSerializer
)
import logging
from django.db import IntegrityError, DatabaseError
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

logger = logging.getLogger(__name__)


class MyProfileView(generics.RetrieveUpdateAPIView):
    """View for current user's profile."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on request method."""
        try:
            if self.request.method == 'GET':
                return PrivateProfileSerializer
            return ProfileUpdateSerializer
        except Exception as e:
            logger.error(f"Error in get_serializer_class: {str(e)}")
            # Fallback to ProfileUpdateSerializer as default
            return ProfileUpdateSerializer
    
    def get_object(self):
        """Get or create profile for current user."""
        try:
            profile, created = UserProfile.objects.get_or_create(user=self.request.user)
            if created:
                logger.info(f"Created new profile for user: {self.request.user.id}")
            return profile
        except IntegrityError as e:
            logger.error(f"Integrity error while creating profile for user {self.request.user.id}: {str(e)}")
            raise ValidationError(
                {"error": "Failed to create profile", "detail": "Profile already exists or database constraint violated"}
            )
        except DatabaseError as e:
            logger.error(f"Database error while accessing profile for user {self.request.user.id}: {str(e)}")
            raise ValidationError(
                {"error": "Database error", "detail": "Unable to access profile at this time"}
            )
        except Exception as e:
            logger.error(f"Unexpected error in get_object for user {self.request.user.id}: {str(e)}", exc_info=True)
            raise ValidationError(
                {"error": "Failed to retrieve profile", "detail": "An unexpected error occurred"}
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Return full profile for owner."""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            logger.info(f"Profile retrieved successfully for user: {request.user.id}")
            return Response(serializer.data)
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error retrieving profile for user {request.user.id}: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to retrieve profile", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def update(self, request, *args, **kwargs):
        """Update profile with error handling."""
        try:
            # Log the update attempt
            logger.info(f"Profile update attempt for user: {request.user.id}")
            
            # Perform the update
            response = super().update(request, *args, **kwargs)
            
            logger.info(f"Profile updated successfully for user: {request.user.id}")
            return response
            
        except ValidationError as e:
            # Re-raise validation errors as they're already formatted
            raise
        except PermissionDenied:
            logger.warning(f"Permission denied for profile update - user: {request.user.id}")
            raise
        except DatabaseError as e:
            logger.error(f"Database error during profile update for user {request.user.id}: {str(e)}")
            return Response(
                {"error": "Database error", "detail": "Unable to update profile at this time"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.error(f"Unexpected error during profile update for user {request.user.id}: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update profile", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def perform_update(self, serializer):
        """Perform update with additional error handling."""
        try:
            serializer.save()
        except IntegrityError as e:
            logger.error(f"Integrity error during profile update: {str(e)}")
            raise ValidationError(
                {"error": "Data integrity error", "detail": "The update violates data constraints"}
            )
        except Exception as e:
            logger.error(f"Error in perform_update: {str(e)}")
            raise ValidationError(
                {"error": "Failed to save profile", "detail": str(e)}
            )


class PublicProfileView(generics.RetrieveAPIView):
    """View for public profile of other users."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PublicProfileSerializer
    queryset = UserProfile.objects.all()
    lookup_field = 'user__id'
    
    def get_object(self):
        """Get profile by user ID with error handling."""
        try:
            user_id = self.kwargs.get('user_id')
            
            if not user_id:
                logger.warning(f"Missing user_id in request from user: {self.request.user.id}")
                raise NotFound({"error": "User ID is required"})
            
            # Validate user_id is a number
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                logger.warning(f"Invalid user_id format: {user_id}")
                raise NotFound({"error": "Invalid user ID format"})
            
            # Don't allow viewing own profile through this view
            if user_id == self.request.user.id:
                logger.info(f"User {self.request.user.id} attempted to view own profile through public endpoint")
                raise PermissionDenied(
                    {"error": "Use MyProfileView to access your own profile"}
                )
            
            profile = get_object_or_404(UserProfile, user__id=user_id)
            logger.info(f"Public profile retrieved for user {user_id} by user {self.request.user.id}")
            return profile
            
        except NotFound:
            raise
        except PermissionDenied:
            raise
        except DatabaseError as e:
            logger.error(f"Database error accessing public profile: {str(e)}")
            raise ValidationError(
                {"error": "Database error", "detail": "Unable to access profile at this time"}
            )
        except Exception as e:
            logger.error(f"Unexpected error in PublicProfileView: {str(e)}", exc_info=True)
            raise ValidationError(
                {"error": "Failed to retrieve profile", "detail": "An unexpected error occurred"}
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve public profile with error handling."""
        try:
            return super().retrieve(request, *args, **kwargs)
        except (NotFound, PermissionDenied, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Error in retrieve method: {str(e)}")
            return Response(
                {"error": "Failed to retrieve profile", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProfileCompletionStatusView(APIView):
    """Check profile completion status."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get profile completion status with error handling."""
        try:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            if created:
                logger.info(f"Created new profile during completion check for user: {request.user.id}")
            
            # Define required fields for each step
            step1_fields = [
                'firstname', 'gender', 'preferred_language'
            ]
            step2_fields = [
                'dateofbirth', 'present_city', 'state', 'nationality'
            ]
            step3_fields = [
                'familyname1', 'religion', 'caste'
            ]
            
            # Calculate completion percentages
            def calculate_completion(fields):
                try:
                    total = len(fields)
                    if total == 0:
                        return 0
                    completed = sum(1 for field in fields if getattr(profile, field, None))
                    return round((completed / total * 100), 2)  # Round to 2 decimal places
                except AttributeError as e:
                    logger.error(f"Error accessing profile field: {str(e)}")
                    return 0
                except Exception as e:
                    logger.error(f"Error calculating completion: {str(e)}")
                    return 0
            
            try:
                step1_pct = calculate_completion(step1_fields)
                step2_pct = calculate_completion(step2_fields)
                step3_pct = calculate_completion(step3_fields)
                total_pct = calculate_completion(step1_fields + step2_fields + step3_fields)
                
                completion = {
                    'step1_percentage': step1_pct,
                    'step2_percentage': step2_pct,
                    'step3_percentage': step3_pct,
                    'total_percentage': total_pct,
                    'is_complete': all([
                        step1_pct == 100,
                        step2_pct == 100,
                        step3_pct == 100
                    ]),
                    'step_status': {
                        'step1_complete': step1_pct == 100,
                        'step2_complete': step2_pct == 100,
                        'step3_complete': step3_pct == 100
                    }
                }
                
                logger.info(f"Profile completion status retrieved for user: {request.user.id}")
                return Response(completion)
                
            except Exception as e:
                logger.error(f"Error calculating completion percentages: {str(e)}")
                # Return default values if calculation fails
                return Response({
                    'step1_percentage': 0,
                    'step2_percentage': 0,
                    'step3_percentage': 0,
                    'total_percentage': 0,
                    'is_complete': False,
                    'step_status': {
                        'step1_complete': False,
                        'step2_complete': False,
                        'step3_complete': False
                    },
                    'error': 'Failed to calculate completion percentages'
                }, status=status.HTTP_200_OK)  # Return 200 with error field instead of failing
                
        except IntegrityError as e:
            logger.error(f"Integrity error in completion status for user {request.user.id}: {str(e)}")
            return Response(
                {"error": "Database integrity error", "detail": "Unable to access profile"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except DatabaseError as e:
            logger.error(f"Database error in completion status for user {request.user.id}: {str(e)}")
            return Response(
                {"error": "Database error", "detail": "Unable to access profile at this time"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.error(f"Unexpected error in completion status for user {request.user.id}: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to check profile completion", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Optional: Add a health check or utility view
class ProfileHealthCheckView(APIView):
    """Health check endpoint for profile service."""
    permission_classes = []  # Public endpoint
    
    def get(self, request):
        """Check if profile service is healthy."""
        try:
            # Try to access the database
            profile_count = UserProfile.objects.count()
            return Response({
                'status': 'healthy',
                'database': 'connected',
                'profile_count': profile_count,
                'timestamp': str(timezone.now())
            })
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return Response({
                'status': 'unhealthy',
                'database': 'disconnected',
                'error': str(e)
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)