from rest_framework import viewsets, status,generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets

from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.permissions import IsAuthenticated,AllowAny
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.core.exceptions import FieldError
from django.db.models import Q, Count
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
import logging
from rest_framework.exceptions import PermissionDenied
import traceback
from .serializers import *

logger = logging.getLogger(__name__)

User = get_user_model()

from .models import StaffPermission, AdminActivityLog, AdminProfile
from apps.relations.models import FixedRelation, RelationLanguagelifestyle, Relationfamilyname8, RelationFamily
from .serializers import (
    AdminLoginSerializer, AdminRegistrationSerializer, StaffCreateSerializer,
    AdminProfileSerializer, AdminUpdateProfileSerializer,
    UserListSerializer, UserStatsSerializer
)
from .permissions import IsAdminUser, IsStaffUser, CanViewUsers,CanManageEvent   


class BaseAPIView(APIView):
    """Base class with common error handling methods"""
    
    def handle_exception(self, exc):
        """Centralized exception handling"""
        if isinstance(exc, (ObjectDoesNotExist, Http404)):
            logger.warning(f"Object not found: {str(exc)}")
            return Response(
                {'error': 'The requested resource was not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        elif isinstance(exc, serializers.ValidationError):
            return Response(
                {'errors': exc.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, PermissionError):
            return Response(
                {'error': 'You do not have permission to perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        elif isinstance(exc, IntegrityError):
            logger.error(f"Database integrity error: {str(exc)}")
            return Response(
                {'error': 'A database error occurred. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, (PermissionError, PermissionDenied)):   # ← add PermissionDenied
            logger.warning(f"Permission denied: {str(exc)}")
            return Response(
                {'error': 'You do not have permission to perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        else:
            logger.error(f"Unexpected error: {str(exc)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'An unexpected error occurred. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0].strip()
            return request.META.get('REMOTE_ADDR')
        except Exception as e:
            logger.error(f"Error getting client IP: {str(e)}")
            return None


class BaseModelViewSet(viewsets.ModelViewSet):
    """Base ModelViewSet with common error handling"""
    
    def handle_exception(self, exc):
        """Centralized exception handling"""
        if isinstance(exc, (ObjectDoesNotExist, Http404)):
            logger.warning(f"Object not found: {str(exc)}")
            return Response(
                {'error': 'The requested resource was not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        elif isinstance(exc, serializers.ValidationError):
            return Response(
                {'errors': exc.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, PermissionError):
            return Response(
                {'error': 'You do not have permission to perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        elif isinstance(exc, IntegrityError):
            logger.error(f"Database integrity error: {str(exc)}")
            return Response(
                {'error': 'A database error occurred. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        elif isinstance(exc, (PermissionError, PermissionDenied)):   # ← add PermissionDenied
            logger.warning(f"Permission denied: {str(exc)}")
            return Response(
                {'error': 'You do not have permission to perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        else:
            logger.error(f"Unexpected error in {self.__class__.__name__}: {str(exc)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'An unexpected error occurred. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0].strip()
            return request.META.get('REMOTE_ADDR')
        except Exception as e:
            logger.error(f"Error getting client IP: {str(e)}")
            return None


class AdminLoginView(BaseAPIView):
    permission_classes = [AllowAny]
    authentication_classes = [] 
    def post(self, request):
        try:
            serializer = AdminLoginSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.validated_data['user']
                # Get admin profile (contains email)
                try:
                    admin_profile = AdminProfile.objects.get(user=user)
                except AdminProfile.DoesNotExist:
                    logger.error(f"Admin profile not found for user {user.id}")
                    return Response(
                        {'error': 'Admin profile not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Get staff permissions
                try:
                    staff_perm = StaffPermission.objects.get(user=user)
                except StaffPermission.DoesNotExist:
                    logger.error(f"Staff permissions not found for user {user.id}")
                    return Response(
                        {'error': 'Staff permissions not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Update last login
                try:
                    user.last_login = timezone.now()
                    user.save(update_fields=['last_login'])
                except Exception as e:
                    logger.error(f"Error updating last login: {str(e)}")
                
                # Generate JWT tokens
                try:
                    refresh = RefreshToken.for_user(user)
                except Exception as e:
                    logger.error(f"Error generating JWT tokens: {str(e)}")
                    return Response(
                        {'error': 'Error generating authentication tokens'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Prepare user data
                profile_picture_url = None
                if admin_profile.profile_picture and hasattr(admin_profile.profile_picture, 'url'):
                    try:
                        profile_picture_url = request.build_absolute_uri(admin_profile.profile_picture.url)
                    except Exception as e:
                        logger.error(f"Error generating profile picture URL: {str(e)}")
                
                user_data = {
                    'id': user.id,
                    'mobile_number': user.mobile_number,
                    'email': admin_profile.email,
                    'full_name': admin_profile.full_name,
                    'admin_id': admin_profile.admin_id,
                    'user_type': staff_perm.user_type,
                    'is_active': staff_perm.is_active,
                    'department': admin_profile.department,
                    'designation': admin_profile.designation,
                    'phone': admin_profile.phone,
                    'profile_picture': profile_picture_url,
                    'created_at': user.created_at,
                    'last_login': user.last_login,
                    'permissions': {
                        'can_view_dashboard': staff_perm.can_view_dashboard,
                        'can_manage_dashboard': staff_perm.can_manage_dashboard,
                        'can_view_users': staff_perm.can_view_users,
                        'can_edit_users': staff_perm.can_edit_users,
                        'can_export_data': staff_perm.can_export_data,
                    }
                }
                
                # Log activity
                try:
                    AdminActivityLog.objects.create(
                        user=user,
                        action='login',
                        description=f'Admin {admin_profile.full_name} logged in',
                        ip_address=self.get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
                    )
                except Exception as e:
                    logger.error(f"Error logging activity: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': 'Login successful',
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': user_data
                })
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in AdminLoginView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Login failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CreateInitialAdminView(BaseAPIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            # Check if admin already exists
            if StaffPermission.objects.filter(user_type='admin').exists():
                return Response(
                    {'error': 'Admin already exists'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = AdminRegistrationSerializer(data=request.data)
            
            if serializer.is_valid():
                try:
                    with transaction.atomic():
                        admin_user = serializer.save()
                        
                        # Get admin profile (contains email)
                        try:
                            admin_profile = AdminProfile.objects.get(user=admin_user)
                        except AdminProfile.DoesNotExist:
                            logger.error(f"Admin profile not found after creation for user {admin_user.id}")
                            return Response(
                                {'error': 'Error creating admin profile'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                            )
                        
                        return Response({
                            'success': True,
                            'message': 'Initial admin created successfully',
                            'admin': {
                                'full_name': admin_profile.full_name,
                                'mobile_number': admin_user.mobile_number,
                                'email': admin_profile.email,
                                'admin_id': admin_profile.admin_id
                            },
                            'login_instructions': 'Use the same credentials to login'
                        }, status=status.HTTP_201_CREATED)
                except IntegrityError as e:
                    logger.error(f"Integrity error creating admin: {str(e)}")
                    return Response(
                        {'error': 'Failed to create admin due to duplicate data'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    logger.error(f"Error creating admin: {str(e)}\n{traceback.format_exc()}")
                    return Response(
                        {'error': 'Failed to create admin. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in CreateInitialAdminView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process request. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AdminTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view that matches the response format of AdminLoginView
    and adds logging.
    """
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            logger.warning(f"Token refresh failed: {str(e)}")
            raise InvalidToken(e.args[0])
        
        # Log successful refresh (optional)
        try:
            # You can extract user from refresh token if needed
            # from rest_framework_simplejwt.tokens import RefreshToken
            # refresh_token = RefreshToken(request.data.get('refresh'))
            # user_id = refresh_token.get('user_id')
            logger.info(f"Token refresh successful")
        except Exception as log_error:
            logger.error(f"Error logging token refresh: {str(log_error)}")
        
        # Return in the same format as login response (optional)
        return Response({
            'success': True,
            'access': str(serializer.validated_data['access']),
            # Optionally return a new refresh token (if rotating)
            # 'refresh': str(serializer.validated_data.get('refresh', ''))
        }, status=status.HTTP_200_OK)
        
        
class AdminProfileView(BaseAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        try:
            user = request.user
            
            try:
                admin_profile = AdminProfile.objects.get(user=user)
            except AdminProfile.DoesNotExist:
                logger.error(f"Admin profile not found for user {user.id}")
                return Response(
                    {'error': 'Admin profile not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            try:
                staff_perm = StaffPermission.objects.get(user=user)
            except StaffPermission.DoesNotExist:
                logger.error(f"Staff permissions not found for user {user.id}")
                return Response(
                    {'error': 'Staff permissions not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            profile_picture_url = None
            if admin_profile.profile_picture and hasattr(admin_profile.profile_picture, 'url'):
                try:
                    profile_picture_url = request.build_absolute_uri(admin_profile.profile_picture.url)
                except Exception as e:
                    logger.error(f"Error generating profile picture URL: {str(e)}")
            
            profile_data = {
                'full_name': admin_profile.full_name,
                'mobile_number': user.mobile_number,
                'email': admin_profile.email,
                'admin_id': admin_profile.admin_id,
                'phone': admin_profile.phone,
                'department': admin_profile.department,
                'designation': admin_profile.designation,
                'profile_picture': profile_picture_url,
                'user_type': staff_perm.user_type,
                'is_active': staff_perm.is_active,
                'created_at': user.created_at,
                'last_login': user.last_login
            }
            
            return Response(profile_data)
        except Exception as e:
            logger.error(f"Unexpected error in AdminProfileView.get: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve profile. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request):
        try:
            user = request.user
            
            try:
                admin_profile = AdminProfile.objects.get(user=user)
            except AdminProfile.DoesNotExist:
                logger.error(f"Admin profile not found for user {user.id}")
                return Response(
                    {'error': 'Admin profile not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = AdminUpdateProfileSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if serializer.is_valid():
                updated_fields = []
                
                try:
                    with transaction.atomic():
                        # Update admin profile fields
                        full_name = serializer.validated_data.get('full_name')
                        if full_name:
                            admin_profile.full_name = full_name
                            updated_fields.append('full_name')
                            
                        profile_picture = serializer.validated_data.get('profile_picture')
                        if profile_picture:
                            admin_profile.profile_picture = profile_picture
                            updated_fields.append('profile_picture')
                        
                        phone = serializer.validated_data.get('phone')
                        if phone:
                            admin_profile.phone = phone
                            updated_fields.append('phone')
                        
                        department = serializer.validated_data.get('department')
                        if department:
                            admin_profile.department = department
                            updated_fields.append('department')
                        
                        designation = serializer.validated_data.get('designation')
                        if designation:
                            admin_profile.designation = designation
                            updated_fields.append('designation')
                        
                        email = serializer.validated_data.get('email')
                        if email and email != admin_profile.email:
                            admin_profile.email = email
                            updated_fields.append('email')
                        
                        admin_profile.save()
                        
                        # Update user mobile number if changed
                        mobile_number = serializer.validated_data.get('mobile_number')
                        if mobile_number and mobile_number != user.mobile_number:
                            user.mobile_number = mobile_number
                            updated_fields.append('mobile_number')
                            user.save()
                        
                        # Log activity
                        try:
                            AdminActivityLog.objects.create(
                                user=user,
                                action='update',
                                description='Updated admin profile',
                                ip_address=self.get_client_ip(request)
                            )
                        except Exception as e:
                            logger.error(f"Error logging activity: {str(e)}")
                        
                        return Response({
                            'success': True,
                            'message': 'Profile updated successfully',
                            'updated_fields': updated_fields
                        })
                except IntegrityError as e:
                    logger.error(f"Integrity error updating profile: {str(e)}")
                    return Response(
                        {'error': 'Failed to update profile due to duplicate data'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    logger.error(f"Error updating profile: {str(e)}\n{traceback.format_exc()}")
                    return Response(
                        {'error': 'Failed to update profile. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in AdminProfileView.put: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process request. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminChangePasswordView(BaseAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request):
        """Change admin password"""
        try:
            user = request.user
            
            serializer = AdminPasswordChangeSerializer(data=request.data)
            if serializer.is_valid():
                old_password = serializer.validated_data['old_password']
                new_password = serializer.validated_data['new_password']
                
                # Verify old password
                if not user.check_password(old_password):
                    return Response(
                        {'error': 'Current password is incorrect'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Set new password
                try:
                    user.set_password(new_password)
                    user.save(update_fields=['password'])
                except Exception as e:
                    logger.error(f"Error setting new password: {str(e)}")
                    return Response(
                        {'error': 'Failed to change password. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Log activity
                try:
                    AdminActivityLog.objects.create(
                        user=user,
                        action='password_change',
                        description='Admin changed password',
                        ip_address=self.get_client_ip(request)
                    )
                except Exception as e:
                    logger.error(f"Error logging password change: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': 'Password changed successfully'
                })
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in AdminChangePasswordView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process request. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StaffManagementViewSet(BaseModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = User.objects.filter(staff_permissions__user_type='staff')
    
    def get_serializer_class(self):
        try:
            if self.action == 'list':
                return UserListSerializer
            elif self.action == 'retrieve':
                return StaffDetailSerializer
            elif self.action in ['create']:
                return StaffCreateSerializer
            elif self.action in ['update', 'partial_update']:
                return StaffUpdateSerializer
            return StaffCreateSerializer
        except Exception as e:
            logger.error(f"Error in get_serializer_class: {str(e)}")
            return StaffCreateSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            if self.action in ['retrieve', 'update', 'partial_update']:
                context['user'] = self.get_object()
            context['request'] = self.request
        except Exception as e:
            logger.error(f"Error in get_serializer_context: {str(e)}")
        return context
    
    def get_queryset(self):
        try:
            queryset = super().get_queryset()
            
            # Filter by is_active status
            is_active = self.request.query_params.get('is_active')
            if is_active is not None:
                if is_active.lower() == 'true':
                    queryset = queryset.filter(staff_permissions__is_active=True)
                elif is_active.lower() == 'false':
                    queryset = queryset.filter(staff_permissions__is_active=False)
            
            # Alternative: filter by status parameter
            status_param = self.request.query_params.get('status')
            if status_param:
                if status_param.lower() == 'active':
                    queryset = queryset.filter(staff_permissions__is_active=True)
                elif status_param.lower() == 'inactive':
                    queryset = queryset.filter(staff_permissions__is_active=False)
            
            # Search functionality
            search = self.request.query_params.get('search')
            if search:
                queryset = queryset.filter(
                    Q(mobile_number__icontains=search) |
                    Q(admin_profile__full_name__icontains=search) |
                    Q(admin_profile__email__icontains=search)
                )
            
            return queryset.select_related('admin_profile', 'staff_permissions')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}\n{traceback.format_exc()}")
            return self.queryset.none()
    
    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            with transaction.atomic():
                staff_user = serializer.save()
                
                # Get admin profile (contains email)
                try:
                    admin_profile = AdminProfile.objects.get(user=staff_user)
                except AdminProfile.DoesNotExist:
                    logger.error(f"Admin profile not found after creation for user {staff_user.id}")
                    return Response(
                        {'error': 'Error creating staff profile'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Log activity
                try:
                    AdminActivityLog.objects.create(
                        user=request.user,
                        action='create',
                        description=f'Created staff: {admin_profile.full_name}',
                        ip_address=self.get_client_ip(request)
                    )
                except Exception as e:
                    logger.error(f"Error logging activity: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': 'Staff created successfully',
                    'staff': {
                        'full_name': admin_profile.full_name,
                        'mobile_number': staff_user.mobile_number,
                        'email': admin_profile.email,
                        'admin_id': admin_profile.admin_id,
                        'user_type': 'staff'
                    }
                }, status=status.HTTP_201_CREATED)
        except serializers.ValidationError as e:
            return Response(
                {'errors': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except IntegrityError as e:
            logger.error(f"Integrity error creating staff: {str(e)}")
            return Response(
                {'error': 'Failed to create staff due to duplicate data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error creating staff: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to create staff. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        try:
            staff_user = self.get_object()
            
            try:
                staff_perm = StaffPermission.objects.get(user=staff_user)
                staff_perm.is_active = not staff_perm.is_active
                staff_perm.save(update_fields=['is_active'])
            except StaffPermission.DoesNotExist:
                logger.error(f"Staff permissions not found for user {staff_user.id}")
                return Response(
                    {'error': 'Staff permissions not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get admin profile for logging
            try:
                admin_profile = AdminProfile.objects.get(user=staff_user)
            except AdminProfile.DoesNotExist:
                logger.error(f"Admin profile not found for user {staff_user.id}")
                admin_profile = None
                profile_name = staff_user.mobile_number
            else:
                profile_name = admin_profile.full_name
            
            # Log activity
            try:
                AdminActivityLog.objects.create(
                    user=request.user,
                    action='status_change',
                    description=f'Changed status for staff {profile_name}',
                    ip_address=self.get_client_ip(request)
                )
            except Exception as e:
                logger.error(f"Error logging activity: {str(e)}")
            
            return Response({
                'success': True,
                'message': f'Staff {"activated" if staff_perm.is_active else "deactivated"}',
                'staff': {
                    'full_name': profile_name,
                    'mobile_number': staff_user.mobile_number,
                    'email': admin_profile.email if admin_profile else '',
                    'is_active': staff_perm.is_active
                }
            })
        except Http404:
            return Response(
                {'error': 'Staff not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error toggling staff active status: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to update staff status. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserManagementViewSet(BaseModelViewSet):
    permission_classes = [IsAuthenticated, CanViewUsers]
    serializer_class = UserListSerializer
    
    def get_serializer_class(self):
        # Use UserDetailSerializer for retrieve action
        if self.action == 'retrieve':
            return UserDetailSerializer
        return UserListSerializer
    
    def get_queryset(self):
        try:
            admin_staff_ids = StaffPermission.objects.filter(
                user_type__in=['admin', 'staff']
            ).values_list('user_id', flat=True)
            
            queryset = User.objects.exclude(id__in=admin_staff_ids)
            
            status_filter = self.request.query_params.get('status')
            search = self.request.query_params.get('search', '')
            
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)
            
            if search:
                queryset = queryset.filter(
                    Q(mobile_number__icontains=search) |
                    Q(email__icontains=search)
                )
            
            return queryset.order_by('-created_at')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}\n{traceback.format_exc()}")
            return User.objects.none()
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        try:
            admin_staff_ids = StaffPermission.objects.filter(
                user_type__in=['admin', 'staff']
            ).values_list('user_id', flat=True)
            
            regular_users = User.objects.exclude(id__in=admin_staff_ids)
            
            total_users = regular_users.count()
            active_users = regular_users.filter(is_active=True).count()
            inactive_users = regular_users.filter(is_active=False).count()
            
            admin_count = StaffPermission.objects.filter(user_type='admin', is_active=True).count()
            staff_count = StaffPermission.objects.filter(user_type='staff', is_active=True).count()
            
            today = timezone.now().date()
            today_users = regular_users.filter(created_at__date=today).count()
            
            week_ago = timezone.now() - timezone.timedelta(days=7)
            week_users = regular_users.filter(created_at__gte=week_ago).count()
            
            stats_data = {
                'total_users': total_users,
                'admin_count': admin_count,
                'staff_count': staff_count,
                'regular_users': total_users,
                'active_users': active_users,
                'today_new_users': today_users,
                'inactive_users': inactive_users,
                'week_new_users': week_users,
                'timestamp': timezone.now()
            }
            
            serializer = UserStatsSerializer(stats_data)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in stats: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve statistics. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Get single user with basic info"""
        try:
            instance = self.get_object()
            
            # Ensure we're not trying to view admin/staff details
            try:
                StaffPermission.objects.get(user=instance)
                return Response(
                    {'error': 'Admin/staff users cannot be viewed from this endpoint'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except StaffPermission.DoesNotExist:
                pass
            
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Http404:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrieving user: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve user. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
            perm = CanViewUsers()
            if not perm.has_permission(request, self):
                return Response(
                    {'error': 'You do not have permission to deactivate users'},
                    status=status.HTTP_403_FORBIDDEN
                )
            try:
                # Remove this block ↓
                # if not self._is_admin():
                #     return Response(
                #         {'error': 'Only admin can deactivate users'},
                #         status=status.HTTP_403_FORBIDDEN
                #     )
                
                user = self.get_object()
                
                # Prevent deactivating admin/staff users
                try:
                    StaffPermission.objects.get(user=user)
                    return Response(
                        {'error': 'Cannot deactivate admin/staff users'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except StaffPermission.DoesNotExist:
                    pass
                
                user.is_active = False
                user.save(update_fields=['is_active'])
                
                # Log activity
                AdminActivityLog.objects.create(
                    user=request.user,
                    action='status_change',
                    description=f'Deactivated user {user.mobile_number}',
                    ip_address=self.get_client_ip(request)
                )
                
                return Response({
                    'success': True,
                    'message': 'User deactivated successfully'
                })
            except Http404:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                logger.error(f"Error deactivating user: {str(e)}\n{traceback.format_exc()}")
                return Response(
                    {'error': 'Failed to deactivate user. Please try again.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
            perm = CanViewUsers()
            if not perm.has_permission(request, self):
                return Response(
                    {'error': 'You do not have permission to deactivate users'},
                    status=status.HTTP_403_FORBIDDEN
                )
            try:
                # Remove this block ↓
                # if not self._is_admin():
                #     return Response(
                #         {'error': 'Only admin can activate users'},
                #         status=status.HTTP_403_FORBIDDEN
                #     )
                
                user = self.get_object()
                user.is_active = True
                user.save(update_fields=['is_active'])
                
                # Log activity
                AdminActivityLog.objects.create(
                    user=request.user,
                    action='status_change',
                    description=f'Activated user {user.mobile_number}',
                    ip_address=self.get_client_ip(request)
                )
                
                return Response({
                    'success': True,
                    'message': 'User activated successfully'
                })
            except Http404:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                logger.error(f"Error activating user: {str(e)}\n{traceback.format_exc()}")
                return Response(
                    {'error': 'Failed to activate user. Please try again.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    
    def _is_admin(self):
        try:
            staff_perm = StaffPermission.objects.get(user=self.request.user)
            return staff_perm.user_type == 'admin'
        except StaffPermission.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking admin status: {str(e)}")
            return False


class RelationManagementPermissionViewSet(BaseModelViewSet):
    """ViewSet for managing relation permissions."""
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = RelationManagementPermissionSerializer
    queryset = RelationManagementPermission.objects.all()
    
    def get_queryset(self):
        try:
            queryset = super().get_queryset()
            
            # Filter by user if provided
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)
            
            return queryset.select_related('user', 'user__admin_profile')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}\n{traceback.format_exc()}")
            return RelationManagementPermission.objects.none()
    
    @action(detail=False, methods=['get'])
    def my_permissions(self, request):
        """Get current user's relation permissions."""
        try:
            try:
                permission = RelationManagementPermission.objects.get(user=request.user)
                serializer = self.get_serializer(permission)
                return Response(serializer.data)
            except RelationManagementPermission.DoesNotExist:
                # Create default permissions if they don't exist
                with transaction.atomic():
                    permission = RelationManagementPermission.objects.create(user=request.user)
                    serializer = self.get_serializer(permission)
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error getting my permissions: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve permissions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RelationAdminActivityLogViewSet(BaseModelViewSet):
    """ViewSet for viewing relation management activity logs."""
    permission_classes = [IsAuthenticated]
    serializer_class = RelationAdminActivityLogSerializer
    queryset = RelationAdminActivityLog.objects.all()
    
    def get_queryset(self):
        try:
            queryset = super().get_queryset()
            
            # Filter by date range
            start_date = self.request.query_params.get('start_date')
            end_date = self.request.query_params.get('end_date')
            action_type = self.request.query_params.get('action')
            relation_code = self.request.query_params.get('relation_code')
            
            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)
            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)
            if action_type:
                queryset = queryset.filter(action=action_type)
            if relation_code:
                queryset = queryset.filter(relation_code=relation_code)
            
            return queryset.select_related('user', 'user__admin_profile').order_by('-created_at')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}\n{traceback.format_exc()}")
            return RelationAdminActivityLog.objects.none()
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of relation activities."""
        try:
            today = timezone.now().date()
            week_ago = today - timezone.timedelta(days=7)
            
            summary = {
                'today': RelationAdminActivityLog.objects.filter(created_at__date=today).count(),
                'this_week': RelationAdminActivityLog.objects.filter(created_at__date__gte=week_ago).count(),
                'by_action': {},
                'top_users': []
            }
            
            # Count by action type
            actions = RelationAdminActivityLog.objects.values('action').annotate(
                count=Count('id')
            ).order_by('-count')[:5]
            
            for action_data in actions:
                summary['by_action'][action_data['action']] = action_data['count']
            
            # Top users by activity
            top_users = RelationAdminActivityLog.objects.values(
                'user__mobile_number', 'user__admin_profile__full_name'
            ).annotate(
                activity_count=Count('id')
            ).order_by('-activity_count')[:5]
            
            for user_data in top_users:
                summary['top_users'].append({
                    'mobile_number': user_data['user__mobile_number'],
                    'full_name': user_data['user__admin_profile__full_name'],
                    'activity_count': user_data['activity_count']
                })
            
            return Response(summary)
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to generate summary. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FixedRelationAdminViewSet(BaseModelViewSet):
    """ViewSet for managing FixedRelations."""
    permission_classes = [IsAuthenticated]  # Only require authentication
    serializer_class = FixedRelationSerializer
    queryset = FixedRelation.objects.all()
    
    def get_permissions(self):
        """Custom permissions based on action."""
        try:
            # Don't require IsAdminUser here - we'll check granular permissions in the methods
            permission_classes = [IsAuthenticated]
            return [permission() for permission in permission_classes]
        except Exception as e:
            logger.error(f"Error in get_permissions: {str(e)}")
            return [IsAuthenticated()] 
    
    def create(self, request, *args, **kwargs):
        """Create a new fixed relation with logging."""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Check if user has permission (admin OR can_manage_fixed_relations)
            if not self._can_manage_fixed_relations(request.user):
                return Response(
                    {'error': 'You do not have permission to create fixed relations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            with transaction.atomic():
                relation = serializer.save()
                
                # Log the activity
                try:
                    RelationAdminActivityLog.objects.create(
                        user=request.user,
                        action='relation_create',
                        description=f'Created fixed relation: {relation.relation_code}',
                        relation_code=relation.relation_code,
                        affected_level='fixed',
                        ip_address=self.get_client_ip(request),
                        metadata={
                            'category': relation.category,
                            'default_english': relation.default_english,
                            'default_tamil': relation.default_tamil
                        }
                    )
                except Exception as e:
                    logger.error(f"Error logging activity: {str(e)}")
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except serializers.ValidationError as e:
            return Response(
                {'errors': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating fixed relation: {str(e)}")
            return Response(
                {'error': 'Failed to create fixed relation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def update(self, request, *args, **kwargs):
        """Update a fixed relation with logging."""
        try:
            # Check permission first
            if not self._can_manage_fixed_relations(request.user):
                return Response(
                    {'error': 'You do not have permission to update fixed relations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating fixed relation: {str(e)}")
            return Response(
                {'error': 'Failed to update fixed relation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    def list(self, request, *args, **kwargs):
        if not self._can_manage_fixed_relations(request.user):
            return Response(
                {'error': 'You do not have permission to view fixed relations'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if not self._can_manage_fixed_relations(request.user):
            return Response(
                {'error': 'You do not have permission to view this fixed relation'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().retrieve(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete a fixed relation with logging."""
        try:
            # Check permission first
            if not self._can_manage_fixed_relations(request.user):
                return Response(
                    {'error': 'You do not have permission to delete fixed relations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting fixed relation: {str(e)}")
            return Response(
                {'error': 'Failed to delete fixed relation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _can_manage_fixed_relations(self, user):
        """Check if user can manage fixed relations."""
        try:
            # Check if user is admin via StaffPermission
            try:
                staff_perm = StaffPermission.objects.get(user=user)
                if staff_perm.user_type == 'admin':
                    return True
            except StaffPermission.DoesNotExist:
                pass
            
            # Check granular permission
            try:
                relation_perm = RelationManagementPermission.objects.get(user=user)
                return relation_perm.can_manage_fixed_relations
            except RelationManagementPermission.DoesNotExist:
                return False
                
        except Exception as e:
            logger.error(f"Error checking fixed relation permission: {str(e)}")
            return False
    
    # Keep your existing _has_relation_permission method or replace it with _can_manage_fixed_relations
    # You can remove _has_relation_permission since we're using _can_manage_fixed_relations instead
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all relation categories."""
        try:
            categories = FixedRelation.RELATION_CATEGORIES
            return Response(dict(categories))
        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
            return Response(
                {'error': 'Failed to retrieve categories. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def overrides(self, request, pk=None):
        """Get all overrides for a specific relation."""
        try:
            relation = self.get_object()
            
            overrides = {
                'language_lifestyle': [],
                'familyname8': [],
                'family': []
            }
            
            # Get language+lifestyle overrides
            try:
                lang_rel_overrides = RelationLanguagelifestyle.objects.filter(relation=relation)
                for override in lang_rel_overrides:
                    overrides['language_lifestyle'].append({
                        'id': override.id,
                        'language': override.language,
                        'lifestyle': override.lifestyle,
                        'label': override.label,
                        'created_at': override.created_at
                    })
            except Exception as e:
                logger.error(f"Error fetching language+lifestyle overrides: {str(e)}")
            
            # Get familyname8 overrides
            try:
                familyname8_overrides = Relationfamilyname8.objects.filter(relation=relation)
                for override in familyname8_overrides:
                    overrides['familyname8'].append({
                        'id': override.id,
                        'language': override.language,
                        'lifestyle': override.lifestyle,
                        'familyname8': override.familyname8,
                        'label': override.label,
                        'created_at': override.created_at
                    })
            except Exception as e:
                logger.error(f"Error fetching familyname8 overrides: {str(e)}")
            
            # Get family overrides
            try:
                family_overrides = RelationFamily.objects.filter(relation=relation)
                for override in family_overrides:
                    overrides['family'].append({
                        'id': override.id,
                        'language': override.language,
                        'lifestyle': override.lifestyle,
                        'familyname8': override.familyname8,
                        'family': override.family,
                        'label': override.label,
                        'created_at': override.created_at
                    })
            except Exception as e:
                logger.error(f"Error fetching family overrides: {str(e)}")
            
            return Response(overrides)
        except Http404:
            return Response(
                {'error': 'Relation not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error getting overrides: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve overrides. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RelationOverrideViewSet(BaseModelViewSet):
    """ViewSet for managing relation overrides."""
    permission_classes = [IsAuthenticated]
    
    def _check_permission(self, user, level):
        """Check if user has permission for specific override level."""
        try:
            relation_perm = RelationManagementPermission.objects.get(user=user)
            
            permission_map = {
                'language_lifestyle': 'can_manage_language_lifestyle',
                'familyname8': 'can_manage_familyname8_overrides',
                'family': 'can_manage_family_overrides'
            }
            
            if level in permission_map:
                return getattr(relation_perm, permission_map[level], False)
            
            return False
        except RelationManagementPermission.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}")
            return False
    
    @action(detail=False, methods=['post'], url_path='create_override')
    def create_override(self, request):
        """Create a relation override at specified level."""
        try:
            level = request.data.get('level')
            
            if not level or level not in ['language_lifestyle', 'familyname8', 'family']:
                return Response(
                    {'error': 'Invalid level specified'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check permissions
            if not self._check_permission(request.user, level):
                return Response(
                    {'error': f'You do not have permission to create {level} overrides'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer_class = {
                'language_lifestyle': LanguagelifestyleOverrideSerializer,
                'familyname8': familyname8OverrideSerializer,
                'family': FamilyOverrideSerializer
            }[level]
            
            serializer = serializer_class(data=request.data)
            if serializer.is_valid():
                data = serializer.validated_data
                
                # Get the fixed relation
                try:
                    relation = FixedRelation.objects.get(relation_code=data['relation_code'])
                except FixedRelation.DoesNotExist:
                    return Response(
                        {'error': f"Relation {data['relation_code']} not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                with transaction.atomic():
                    # Create the override based on level
                    if level == 'language_lifestyle':
                        override, created = RelationLanguagelifestyle.objects.update_or_create(
                            relation=relation,
                            language=data['language'],
                            lifestyle=data['lifestyle'],
                            defaults={'label': data['label']}
                        )
                    elif level == 'familyname8':
                        override, created = Relationfamilyname8.objects.update_or_create(
                            relation=relation,
                            language=data['language'],
                            lifestyle=data['lifestyle'],
                            familyname8=data['familyname8'],
                            defaults={'label': data['label']}
                        )
                    else:  # family
                        override, created = RelationFamily.objects.update_or_create(
                            relation=relation,
                            language=data['language'],
                            lifestyle=data['lifestyle'],
                            familyname8=data['familyname8'],
                            family=data['family'],
                            defaults={'label': data['label']}
                        )
                    
                    # Log the activity
                    try:
                        action_type = 'override_create' if created else 'override_update'
                        RelationAdminActivityLog.objects.create(
                            user=request.user,
                            action=action_type,
                            description=f'{"Created" if created else "Updated"} {level} override for {relation.relation_code}',
                            relation_code=relation.relation_code,
                            affected_level=level,
                            ip_address=self.get_client_ip(request),
                            metadata={
                                'language': data['language'],
                                'lifestyle': data['lifestyle'],
                                'label': data['label'],
                                'is_new': created
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error logging activity: {str(e)}")
                    
                    return Response({
                        'success': True,
                        'message': f'Override {"created" if created else "updated"} successfully',
                        'override_id': override.id,
                        'level': level
                    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating override: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to create override. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple overrides in bulk."""
        try:
            serializer = BulkOverrideSerializer(data=request.data)
            if serializer.is_valid():
                data = serializer.validated_data
                level = data['level']
                
                # Check permissions
                if not self._check_permission(request.user, level):
                    return Response(
                        {'error': f'You do not have permission to create {level} overrides'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                results = {
                    'success': [],
                    'failed': []
                }
                
                with transaction.atomic():
                    for i, override_data in enumerate(data['overrides']):
                        try:
                            # Get the fixed relation
                            try:
                                relation = FixedRelation.objects.get(
                                    relation_code=override_data['relation_code']
                                )
                            except FixedRelation.DoesNotExist:
                                results['failed'].append({
                                    'index': i,
                                    'relation_code': override_data.get('relation_code', 'unknown'),
                                    'error': f"Relation not found: {override_data.get('relation_code')}"
                                })
                                continue
                            
                            # Create override based on level
                            if level == 'language_lifestyle':
                                obj, created = RelationLanguagelifestyle.objects.update_or_create(
                                    relation=relation,
                                    language=override_data['language'],
                                    lifestyle=override_data['lifestyle'],
                                    defaults={'label': override_data['label']}
                                )
                            elif level == 'familyname8':
                                obj, created = Relationfamilyname8.objects.update_or_create(
                                    relation=relation,
                                    language=override_data['language'],
                                    lifestyle=override_data['lifestyle'],
                                    familyname8=override_data['familyname8'],
                                    defaults={'label': override_data['label']}
                                )
                            else:  # family
                                obj, created = RelationFamily.objects.update_or_create(
                                    relation=relation,
                                    language=override_data['language'],
                                    lifestyle=override_data['lifestyle'],
                                    familyname8=override_data['familyname8'],
                                    family=override_data['family'],
                                    defaults={'label': override_data['label']}
                                )
                            
                            results['success'].append({
                                'index': i,
                                'relation_code': override_data['relation_code'],
                                'created': created
                            })
                            
                        except KeyError as e:
                            results['failed'].append({
                                'index': i,
                                'relation_code': override_data.get('relation_code', 'unknown'),
                                'error': f"Missing required field: {str(e)}"
                            })
                        except IntegrityError as e:
                            results['failed'].append({
                                'index': i,
                                'relation_code': override_data.get('relation_code', 'unknown'),
                                'error': f"Database integrity error: {str(e)}"
                            })
                        except Exception as e:
                            results['failed'].append({
                                'index': i,
                                'relation_code': override_data.get('relation_code', 'unknown'),
                                'error': str(e)
                            })
                    
                    # Log bulk activity
                    try:
                        RelationAdminActivityLog.objects.create(
                            user=request.user,
                            action='bulk_import',
                            description=f'Bulk imported {len(results["success"])} overrides at {level} level',
                            ip_address=self.get_client_ip(request),
                            metadata={
                                'level': level,
                                'total': len(data['overrides']),
                                'success': len(results['success']),
                                'failed': len(results['failed'])
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error logging bulk activity: {str(e)}")
                
                return Response({
                    'success': True,
                    'results': results,
                    'summary': {
                        'total': len(data['overrides']),
                        'success': len(results['success']),
                        'failed': len(results['failed'])
                    }
                })
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in bulk_create: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process bulk import. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['delete'])
    def delete_override(self, request):
        """Delete a relation override."""
        try:
            level = request.query_params.get('level')
            override_id = request.query_params.get('id')
            
            if not level or level not in ['language_lifestyle', 'familyname8', 'family']:
                return Response(
                    {'error': 'Invalid level specified'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not override_id:
                return Response(
                    {'error': 'Override ID is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check permissions
            if not self._check_permission(request.user, level):
                return Response(
                    {'error': f'You do not have permission to delete {level} overrides'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get the model based on level
            model_map = {
                'language_lifestyle': RelationLanguagelifestyle,
                'familyname8': Relationfamilyname8,
                'family': RelationFamily
            }
            
            model = model_map[level]
            
            try:
                override = model.objects.get(id=override_id)
                relation_code = override.relation.relation_code
                
                # Delete the override
                override.delete()
                
                # Log the activity
                try:
                    RelationAdminActivityLog.objects.create(
                        user=request.user,
                        action='override_delete',
                        description=f'Deleted {level} override for {relation_code}',
                        relation_code=relation_code,
                        affected_level=level,
                        ip_address=self.get_client_ip(request)
                    )
                except Exception as e:
                    logger.error(f"Error logging activity: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': f'Override deleted successfully'
                })
                
            except model.DoesNotExist:
                return Response(
                    {'error': f'Override not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Exception as e:
            logger.error(f"Error deleting override: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to delete override. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search for overrides."""
        try:
            level = request.query_params.get('level', 'all')
            language = request.query_params.get('language')
            lifestyle = request.query_params.get('lifestyle')
            familyname8 = request.query_params.get('familyname8')
            family = request.query_params.get('family')
            relation_code = request.query_params.get('relation_code')
            
            results = []
            
            # Search language+lifestyle overrides
            if level in ['all', 'language_lifestyle']:
                try:
                    queryset = RelationLanguagelifestyle.objects.all()
                    
                    if language:
                        queryset = queryset.filter(language=language)
                    if lifestyle:
                        queryset = queryset.filter(lifestyle=lifestyle)
                    if relation_code:
                        queryset = queryset.filter(relation__relation_code=relation_code)
                    
                    for item in queryset.select_related('relation'):
                        results.append({
                            'id': item.id,
                            'level': 'language_lifestyle',
                            'relation_code': item.relation.relation_code,
                            'language': item.language,
                            'lifestyle': item.lifestyle,
                            'label': item.label,
                            'created_at': item.created_at,
                            'default_english': item.relation.default_english,
                            'default_tamil': item.relation.default_tamil
                        })
                except Exception as e:
                    logger.error(f"Error searching language+lifestyle overrides: {str(e)}")
            
            # Search familyname8 overrides
            if level in ['all', 'familyname8']:
                try:
                    queryset = Relationfamilyname8.objects.all()
                    
                    if language:
                        queryset = queryset.filter(language=language)
                    if lifestyle:
                        queryset = queryset.filter(lifestyle=lifestyle)
                    if familyname8:
                        queryset = queryset.filter(familyname8=familyname8)
                    if relation_code:
                        queryset = queryset.filter(relation__relation_code=relation_code)
                    
                    for item in queryset.select_related('relation'):
                        results.append({
                            'id': item.id,
                            'level': 'familyname8',
                            'relation_code': item.relation.relation_code,
                            'language': item.language,
                            'lifestyle': item.lifestyle,
                            'familyname8': item.familyname8,
                            'label': item.label,
                            'created_at': item.created_at,
                            'default_english': item.relation.default_english,
                            'default_tamil': item.relation.default_tamil
                        })
                except Exception as e:
                    logger.error(f"Error searching familyname8 overrides: {str(e)}")
            
            # Search family overrides
            if level in ['all', 'family']:
                try:
                    queryset = RelationFamily.objects.all()
                    
                    if language:
                        queryset = queryset.filter(language=language)
                    if lifestyle:
                        queryset = queryset.filter(lifestyle=lifestyle)
                    if familyname8:
                        queryset = queryset.filter(familyname8=familyname8)
                    if family:
                        queryset = queryset.filter(family=family)
                    if relation_code:
                        queryset = queryset.filter(relation__relation_code=relation_code)
                    
                    for item in queryset.select_related('relation'):
                        results.append({
                            'id': item.id,
                            'level': 'family',
                            'relation_code': item.relation.relation_code,
                            'language': item.language,
                            'lifestyle': item.lifestyle,
                            'familyname8': item.familyname8,
                            'family': item.family,
                            'label': item.label,
                            'created_at': item.created_at,
                            'default_english': item.relation.default_english,
                            'default_tamil': item.relation.default_tamil
                        })
                except Exception as e:
                    logger.error(f"Error searching family overrides: {str(e)}")
            
            # Sort by creation date
            results.sort(key=lambda x: x['created_at'], reverse=True)
            
            return Response({
                'count': len(results),
                'results': results
            })
        except Exception as e:
            logger.error(f"Error in search: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to search overrides. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RelationLabelTestView(generics.GenericAPIView):
    """View for testing relation label resolution."""
    permission_classes = [IsAuthenticated]
    serializer_class = RelationLabelTestSerializer
    
    def post(self, request):
        """Test relation label resolution with given context."""
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                data = serializer.validated_data
                
                # Get label using RelationLabelService
                try:
                    label_info = RelationLabelService.get_relation_label(
                        relation_code=data['relation_code'],
                        language=data['language'],
                        lifestyle=data['lifestyle'],
                        familyname8=data['familyname8'],
                        family_name=data.get('family', '')
                    )
                except Exception as e:
                    logger.error(f"Error getting relation label: {str(e)}")
                    return Response(
                        {'error': 'Failed to resolve relation label'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Get the relation
                try:
                    relation = FixedRelation.objects.get(relation_code=data['relation_code'])
                except FixedRelation.DoesNotExist:
                    return Response(
                        {'error': f"Relation {data['relation_code']} not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Check for overrides
                family_override = None
                if data.get('family'):
                    try:
                        family_override = RelationFamily.objects.filter(
                            relation=relation,
                            language=data['language'],
                            lifestyle=data['lifestyle'],
                            familyname8=data['familyname8'],
                            family=data['family']
                        ).first()
                    except Exception as e:
                        logger.error(f"Error checking family override: {str(e)}")
                
                familyname8_override = None
                try:
                    familyname8_override = Relationfamilyname8.objects.filter(
                        relation=relation,
                        language=data['language'],
                        lifestyle=data['lifestyle'],
                        familyname8=data['familyname8']
                    ).first()
                except Exception as e:
                    logger.error(f"Error checking familyname8 override: {str(e)}")
                
                lang_rel_override = None
                try:
                    lang_rel_override = RelationLanguagelifestyle.objects.filter(
                        relation=relation,
                        language=data['language'],
                        lifestyle=data['lifestyle']
                    ).first()
                except Exception as e:
                    logger.error(f"Error checking language+lifestyle override: {str(e)}")
                
                # Prepare response
                response_data = {
                    'request_context': data,
                    'resolved_label': label_info['label'],
                    'resolution_level': label_info['level'],
                    'source': label_info.get('source', 'unknown'),
                    'available_overrides': {
                        'family': {
                            'exists': family_override is not None,
                            'label': family_override.label if family_override else None
                        },
                        'familyname8': {
                            'exists': familyname8_override is not None,
                            'label': familyname8_override.label if familyname8_override else None
                        },
                        'language_lifestyle': {
                            'exists': lang_rel_override is not None,
                            'label': lang_rel_override.label if lang_rel_override else None
                        },
                        'defaults': {
                            'english': relation.default_english,
                            'tamil': relation.default_tamil
                        }
                    },
                    'hierarchy_used': [
                        {'level': 'family', 'used': family_override is not None},
                        {'level': 'familyname8', 'used': familyname8_override is not None and family_override is None},
                        {'level': 'language_lifestyle', 'used': lang_rel_override is not None and familyname8_override is None and family_override is None},
                        {'level': 'default', 'used': all([
                            family_override is None,
                            familyname8_override is None,
                            lang_rel_override is None
                        ])}
                    ]
                }
                
                return Response(response_data)
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in RelationLabelTestView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to test relation label. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RelationAnalyticsView(generics.GenericAPIView):
    """View for relation analytics and insights."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get relation analytics."""
        try:
            # Check if user has permission to view analytics
            try:
                relation_perm = RelationManagementPermission.objects.get(user=request.user)
                if not relation_perm.can_view_relation_analytics:
                    return Response(
                        {'error': 'You do not have permission to view relation analytics'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except RelationManagementPermission.DoesNotExist:
                return Response(
                    {'error': 'Relation permissions not found'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Calculate analytics
            total_relations = FixedRelation.objects.count()
            total_overrides = (
                RelationLanguagelifestyle.objects.count() +
                Relationfamilyname8.objects.count() +
                RelationFamily.objects.count()
            )
            
            overrides_by_level = {
                'language_lifestyle': RelationLanguagelifestyle.objects.count(),
                'familyname8': Relationfamilyname8.objects.count(),
                'family': RelationFamily.objects.count()
            }
            
            # Most overridden relations
            most_overridden = []
            try:
                relations = FixedRelation.objects.annotate(
                    total_overrides=Count('family_labels') + Count('familyname8_labels') + Count('language_lifestyle_labels')
                ).order_by('-total_overrides')[:10]
                
                for relation in relations:
                    most_overridden.append({
                        'relation_code': relation.relation_code,
                        'default_english': relation.default_english,
                        'total_overrides': relation.total_overrides,
                        'by_level': {
                            'family': relation.family_labels.count(),
                            'familyname8': relation.familyname8_labels.count(),
                            'language_lifestyle': relation.language_lifestyle_labels.count()
                        }
                    })
            except Exception as e:
                logger.error(f"Error calculating most overridden relations: {str(e)}")
            
            # Recent activity
            recent_activity = []
            try:
                recent = RelationAdminActivityLog.objects.order_by('-created_at')[:10]
                activity_serializer = RelationAdminActivityLogSerializer(recent, many=True)
                recent_activity = activity_serializer.data
            except Exception as e:
                logger.error(f"Error fetching recent activity: {str(e)}")
            
            # Categories breakdown
            categories_breakdown = {}
            try:
                for code, name in FixedRelation.RELATION_CATEGORIES:
                    count = FixedRelation.objects.filter(category=code).count()
                    categories_breakdown[name] = count
            except Exception as e:
                logger.error(f"Error calculating categories breakdown: {str(e)}")
            
            analytics_data = {
                'total_relations': total_relations,
                'total_overrides': total_overrides,
                'overrides_by_level': overrides_by_level,
                'most_overridden_relations': most_overridden,
                'recent_activity': recent_activity,
                'categories_breakdown': categories_breakdown,
                'coverage_rate': round((total_overrides / (total_relations * 3)) * 100, 2) if total_relations > 0 else 0
            }
            
            serializer = RelationAnalyticsSerializer(analytics_data)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in RelationAnalyticsView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve analytics. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RelationAutoSuggestViewSet(BaseModelViewSet):
    """Auto-suggestion endpoints for relation fields."""
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['get'])
    def familyname8(self, request):
        """Auto-suggest familyname8 values (starts with query)."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)  # Cap at 50
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            
            # Get distinct familyname8 values that START with query
            try:
                familyname8_results = Relationfamilyname8.objects.filter(
                    familyname8__istartswith=query
                ).values('familyname8').annotate(
                    count=Count('id'),
                    lifestyles=Count('lifestyle', distinct=True)
                ).order_by('-count', 'familyname8')[:limit]
                
                suggestions = [
                    {
                        'value': item['familyname8'],
                        'label': item['familyname8'],
                        'count': item['count'],
                        'lifestyles': item['lifestyles']
                    }
                    for item in familyname8_results
                ]
            except Exception as e:
                logger.error(f"Error fetching familyname8 suggestions (starts with): {str(e)}")
            
            # If no results with "starts with", fall back to "contains"
            if not suggestions and len(query) >= 2:
                try:
                    familyname8_results = Relationfamilyname8.objects.filter(
                        familyname8__icontains=query
                    ).values('familyname8').annotate(
                        count=Count('id'),
                        lifestyles=Count('lifestyle', distinct=True)
                    ).order_by('-count', 'familyname8')[:limit]
                    
                    suggestions = [
                        {
                            'value': item['familyname8'],
                            'label': item['familyname8'],
                            'count': item['count'],
                            'lifestyles': item['lifestyles']
                        }
                        for item in familyname8_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching familyname8 suggestions (contains): {str(e)}")
            
            return Response({
                'query': query,
                'suggestions': suggestions
            })
        except Exception as e:
            logger.error(f"Error in familyname8 auto-suggest: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def family(self, request):
        """Auto-suggest family values (starts with query)."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)  # Cap at 50
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            
            # Get distinct family values that START with query
            try:
                family_results = RelationFamily.objects.filter(
                    family__istartswith=query
                ).values('family', 'familyname8', 'lifestyle').annotate(
                    count=Count('id')
                ).order_by('-count', 'family')[:limit]
                
                suggestions = [
                    {
                        'value': item['family'],
                        'label': item['family'],
                        'familyname8': item['familyname8'],
                        'lifestyle': item['lifestyle'],
                        'count': item['count']
                    }
                    for item in family_results
                ]
            except Exception as e:
                logger.error(f"Error fetching family suggestions (starts with): {str(e)}")
            
            # Fallback to contains if no results
            if not suggestions and len(query) >= 2:
                try:
                    family_results = RelationFamily.objects.filter(
                        family__icontains=query
                    ).values('family', 'familyname8', 'lifestyle').annotate(
                        count=Count('id')
                    ).order_by('-count', 'family')[:limit]
                    
                    suggestions = [
                        {
                            'value': item['family'],
                            'label': item['family'],
                            'familyname8': item['familyname8'],
                            'lifestyle': item['lifestyle'],
                            'count': item['count']
                        }
                        for item in family_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching family suggestions (contains): {str(e)}")
            
            return Response({
                'query': query,
                'suggestions': suggestions
            })
        except Exception as e:
            logger.error(f"Error in family auto-suggest: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def relation(self, request):
        """Auto-suggest relation codes (starts with query)."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)  # Cap at 50
            
            if len(query) < 1:
                return Response({'suggestions': []})
            
            suggestions = []
            
            # Search in relation codes (starts with)
            try:
                relation_results = FixedRelation.objects.filter(
                    Q(relation_code__istartswith=query) |
                    Q(default_english__istartswith=query) |
                    Q(default_tamil__istartswith=query)
                ).order_by('relation_code')[:limit]
                
                suggestions = [
                    {
                        'value': rel.relation_code,
                        'label': f"{rel.relation_code} - {rel.default_english}",
                        'english': rel.default_english,
                        'tamil': rel.default_tamil,
                        'category': rel.get_category_display(),
                        'overrides': (
                            rel.family_labels.count() +
                            rel.familyname8_labels.count() +
                            rel.language_lifestyle_labels.count()
                        )
                    }
                    for rel in relation_results
                ]
            except Exception as e:
                logger.error(f"Error fetching relation suggestions (starts with): {str(e)}")
            
            # Fallback to contains
            if not suggestions and len(query) >= 2:
                try:
                    relation_results = FixedRelation.objects.filter(
                        Q(relation_code__icontains=query) |
                        Q(default_english__icontains=query) |
                        Q(default_tamil__icontains=query)
                    ).order_by('relation_code')[:limit]
                    
                    suggestions = [
                        {
                            'value': rel.relation_code,
                            'label': f"{rel.relation_code} - {rel.default_english}",
                            'english': rel.default_english,
                            'tamil': rel.default_tamil,
                            'category': rel.get_category_display(),
                            'overrides': (
                                rel.family_labels.count() +
                                rel.familyname8_labels.count() +
                                rel.language_lifestyle_labels.count()
                            )
                        }
                        for rel in relation_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching relation suggestions (contains): {str(e)}")
            
            return Response({
                'query': query,
                'suggestions': suggestions
            })
        except Exception as e:
            logger.error(f"Error in relation auto-suggest: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def language(self, request):
        """Auto-suggest language values."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)  # Cap at 50
            
            languages = []
            
            if len(query) < 2:
                # Return all languages if query is short
                try:
                    lang_list = RelationLanguagelifestyle.objects.values_list(
                        'language', flat=True
                    ).distinct().order_by('language')[:limit]
                    
                    languages = [{'value': lang, 'label': lang} for lang in lang_list]
                except Exception as e:
                    logger.error(f"Error fetching all languages: {str(e)}")
            else:
                # Filter by query (starts with)
                try:
                    lang_list = RelationLanguagelifestyle.objects.filter(
                        language__istartswith=query
                    ).values_list('language', flat=True).distinct().order_by('language')[:limit]
                    
                    languages = [{'value': lang, 'label': lang} for lang in lang_list]
                except Exception as e:
                    logger.error(f"Error fetching filtered languages: {str(e)}")
            
            return Response({
                'query': query,
                'suggestions': languages
            })
        except Exception as e:
            logger.error(f"Error in language auto-suggest: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def lifestyle(self, request):
        """Auto-suggest lifestyle values."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)  # Cap at 50
            
            # Get from multiple sources
            lifestyle_set = set()
            
            # From language+lifestyle overrides
            try:
                lifestyles_lr = RelationLanguagelifestyle.objects.filter(
                    lifestyle__istartswith=query
                ).values_list('lifestyle', flat=True).distinct()
                lifestyle_set.update(lifestyles_lr)
            except Exception as e:
                logger.error(f"Error fetching lifestyles from language+lifestyle: {str(e)}")
            
            # From familyname8 overrides
            try:
                lifestyles_familyname8 = Relationfamilyname8.objects.filter(
                    lifestyle__istartswith=query
                ).values_list('lifestyle', flat=True).distinct()
                lifestyle_set.update(lifestyles_familyname8)
            except Exception as e:
                logger.error(f"Error fetching lifestyles from familyname8: {str(e)}")
            
            # If no results with "starts with", try "contains"
            if not lifestyle_set and len(query) >= 2:
                try:
                    lifestyles_lr = RelationLanguagelifestyle.objects.filter(
                        lifestyle__icontains=query
                    ).values_list('lifestyle', flat=True).distinct()
                    lifestyle_set.update(lifestyles_lr)
                except Exception as e:
                    logger.error(f"Error fetching lifestyles from language+lifestyle (contains): {str(e)}")
                
                try:
                    lifestyles_familyname8 = Relationfamilyname8.objects.filter(
                        lifestyle__icontains=query
                    ).values_list('lifestyle', flat=True).distinct()
                    lifestyle_set.update(lifestyles_familyname8)
                except Exception as e:
                    logger.error(f"Error fetching lifestyles from familyname8 (contains): {str(e)}")
            
            # Sort alphabetically
            sorted_lifestyles = sorted(list(lifestyle_set))[:limit]
            
            results = [{'value': rel, 'label': rel} for rel in sorted_lifestyles]
            
            return Response({
                'query': query,
                'suggestions': results
            })
        except Exception as e:
            logger.error(f"Error in lifestyle auto-suggest: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    
    def get_queryset(self):
        try:
            queryset = super().get_queryset()
            
            # Filter by user
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)
            
            # Filter by action
            action = self.request.query_params.get('action')
            if action:
                queryset = queryset.filter(action=action)
            
            # Filter by date range
            start_date = self.request.query_params.get('start_date')
            end_date = self.request.query_params.get('end_date')
            if start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)
            if end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)
            
            # Filter by user type (admin/staff)
            user_type = self.request.query_params.get('user_type')
            if user_type:
                queryset = queryset.filter(user__staff_permissions__user_type=user_type)
            
            return queryset.select_related('user', 'user__admin_profile')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}\n{traceback.format_exc()}")
            return AdminActivityLog.objects.none()
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of admin/staff activities."""
        try:
            today = timezone.now().date()
            week_ago = today - timezone.timedelta(days=7)
            month_ago = today - timezone.timedelta(days=30)
            
            summary = {
                'total_logs': AdminActivityLog.objects.count(),
                'today': AdminActivityLog.objects.filter(created_at__date=today).count(),
                'this_week': AdminActivityLog.objects.filter(created_at__date__gte=week_ago).count(),
                'this_month': AdminActivityLog.objects.filter(created_at__date__gte=month_ago).count(),
                'by_action': {},
                'by_user_type': {
                    'admin': AdminActivityLog.objects.filter(user__staff_permissions__user_type='admin').count(),
                    'staff': AdminActivityLog.objects.filter(user__staff_permissions__user_type='staff').count(),
                },
                'top_users': [],
                'recent_activities': []
            }
            
            # Count by action type
            try:
                actions = AdminActivityLog.objects.values('action').annotate(
                    count=Count('id')
                ).order_by('-count')
                
                for action_data in actions:
                    summary['by_action'][action_data['action']] = action_data['count']
            except Exception as e:
                logger.error(f"Error counting by action: {str(e)}")
            
            # Top users by activity
            try:
                top_users = AdminActivityLog.objects.values(
                    'user__mobile_number', 
                    'user__admin_profile__full_name',
                    'user__staff_permissions__user_type'
                ).annotate(
                    activity_count=Count('id')
                ).order_by('-activity_count')[:5]
                
                for user_data in top_users:
                    summary['top_users'].append({
                        'mobile_number': user_data['user__mobile_number'],
                        'full_name': user_data['user__admin_profile__full_name'],
                        'user_type': user_data['user__staff_permissions__user_type'],
                        'activity_count': user_data['activity_count']
                    })
            except Exception as e:
                logger.error(f"Error getting top users: {str(e)}")
            
            # Recent activities
            try:
                recent = AdminActivityLog.objects.order_by('-created_at')[:10]
                recent_serializer = AdminActivityLogSerializer(recent, many=True, context={'request': request})
                summary['recent_activities'] = recent_serializer.data
            except Exception as e:
                logger.error(f"Error getting recent activities: {str(e)}")
            
            return Response(summary)
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to generate summary. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StaffSelfProfileView(BaseAPIView):
    """Allow staff to edit their own complete profile including mobile and email"""
    permission_classes = [IsAuthenticated, IsStaffUser]
    
    def get(self, request):
        """Get staff's own profile"""
        try:
            user = request.user
            
            try:
                admin_profile = AdminProfile.objects.get(user=user)
            except AdminProfile.DoesNotExist:
                logger.error(f"Admin profile not found for staff {user.id}")
                return Response(
                    {'error': 'Profile not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            try:
                staff_perm = StaffPermission.objects.get(user=user)
            except StaffPermission.DoesNotExist:
                logger.error(f"Staff permissions not found for user {user.id}")
                staff_perm = None
            
            profile_picture_url = None
            if admin_profile.profile_picture and hasattr(admin_profile.profile_picture, 'url'):
                try:
                    profile_picture_url = request.build_absolute_uri(admin_profile.profile_picture.url)
                except ValueError:
                    # File doesn't exist
                    profile_picture_url = None
                except Exception as e:
                    logger.error(f"Error generating profile picture URL: {str(e)}")
            
            permissions = {}
            if staff_perm:
                permissions = {
                    'can_view_dashboard': staff_perm.can_view_dashboard,
                    # 'can_manage_dashboard': staff_perm.can_manage_dashboard,
                    'can_view_users': staff_perm.can_view_users,
                    'can_edit_users': staff_perm.can_edit_users,
                    # 'can_export_data': staff_perm.can_export_data,
                    'chat_management':staff_perm.can_manage_chat,
                    'post_management':staff_perm.can_manage_post,
                    'event_management': staff_perm.can_manage_event, 
                    # 'manage_fixed_relations':staff_perm.can_manage_chat,
                    

                    
                }
            
            return Response({
                'id': user.id,
                'mobile_number': user.mobile_number,
                'full_name': admin_profile.full_name,
                'email': admin_profile.email,
                'phone': admin_profile.phone,
                'department': admin_profile.department,
                'designation': admin_profile.designation,
                'profile_picture': profile_picture_url,
                'admin_id': admin_profile.admin_id,
                'user_type': staff_perm.user_type if staff_perm else 'staff',
                'is_active': staff_perm.is_active if staff_perm else True,
                'permissions': permissions
            })
        except Exception as e:
            logger.error(f"Error in StaffSelfProfileView.get: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to retrieve profile. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request):
        """Update own profile - ALL fields including mobile and email"""
        try:
            user = request.user
            
            try:
                admin_profile = AdminProfile.objects.get(user=user)
            except AdminProfile.DoesNotExist:
                logger.error(f"Admin profile not found for staff {user.id}")
                return Response(
                    {'error': 'Profile not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = StaffSelfUpdateSerializer(
                data=request.data,
                context={'request': request, 'user': user},
                partial=True
            )
            
            if serializer.is_valid():
                updated_fields = []
                
                try:
                    with transaction.atomic():
                        # 1. Update User model (mobile number)
                        if 'mobile_number' in serializer.validated_data:
                            new_mobile = serializer.validated_data['mobile_number']
                            if new_mobile != user.mobile_number:
                                user.mobile_number = new_mobile
                                updated_fields.append('mobile_number')
                        
                        # 2. Update AdminProfile
                        profile_fields = ['full_name', 'email', 'phone', 'department', 'designation', 'profile_picture']
                        for field in profile_fields:
                            if field in serializer.validated_data:
                                setattr(admin_profile, field, serializer.validated_data[field])
                                updated_fields.append(field)
                        
                        # Save changes
                        if 'mobile_number' in serializer.validated_data:
                            user.save(update_fields=['mobile_number'])
                        admin_profile.save()
                        
                        # Log activity
                        try:
                            AdminActivityLog.objects.create(
                                user=user,
                                action='self_profile_update',
                                description=f'Staff updated own profile: {", ".join(updated_fields)}',
                                ip_address=self.get_client_ip(request)
                            )
                        except Exception as e:
                            logger.error(f"Error logging activity: {str(e)}")
                        
                        return Response({
                            'success': True,
                            'message': 'Profile updated successfully',
                            'updated_fields': updated_fields
                        })
                except IntegrityError as e:
                    logger.error(f"Integrity error updating profile: {str(e)}")
                    return Response(
                        {'error': 'Failed to update profile due to duplicate data'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    logger.error(f"Error updating profile: {str(e)}\n{traceback.format_exc()}")
                    return Response(
                        {'error': 'Failed to update profile. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in StaffSelfProfileView.patch: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process request. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StaffSelfChangePasswordView(BaseAPIView):
    """Allow staff to change their own password"""
    permission_classes = [IsAuthenticated, IsStaffUser]
    
    def post(self, request):
        try:
            user = request.user
            
            serializer = AdminPasswordChangeSerializer(data=request.data)
            if serializer.is_valid():
                old_password = serializer.validated_data['old_password']
                new_password = serializer.validated_data['new_password']
                
                if not user.check_password(old_password):
                    return Response(
                        {'error': 'Current password is incorrect'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    user.set_password(new_password)
                    user.save(update_fields=['password'])
                except Exception as e:
                    logger.error(f"Error setting new password: {str(e)}")
                    return Response(
                        {'error': 'Failed to change password. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Log activity
                try:
                    AdminActivityLog.objects.create(
                        user=user,
                        action='self_password_change',
                        description='Staff changed own password',
                        ip_address=self.get_client_ip(request)
                    )
                except Exception as e:
                    logger.error(f"Error logging activity: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': 'Password changed successfully'
                })
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in StaffSelfChangePasswordView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to process request. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminDashboardView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # Parse filter parameters
            filter_serializer = DashboardFilterSerializer(data=request.query_params)
            filter_serializer.is_valid(raise_exception=True)
            filters = filter_serializer.validated_data
            
            try:
                staff_perm = StaffPermission.objects.get(user=user)
            except StaffPermission.DoesNotExist:
                logger.error(f"Staff permissions not found for user {user.id}")
                return Response(
                    {'error': 'Permission not found'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if staff_perm.user_type == 'admin':
                return self._get_admin_dashboard_data(request, filters)
            elif staff_perm.user_type == 'staff':
                if not staff_perm.can_view_dashboard:
                    return Response(
                        {'error': 'You do not have permission to view dashboard'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                return self._get_staff_dashboard_data(request, filters)
            else:
                return Response(
                    {'error': 'Invalid user type'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except serializers.ValidationError as e:
            return Response(
                {'errors': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in AdminDashboardView: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to load dashboard data. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _apply_date_filter(self, queryset, filters, date_field='created_at'):
        """Apply date filtering to any queryset"""
        try:
            period = filters.get('period', 'all')
            
            if period == 'all':
                return queryset
            
            now = timezone.now()
            today = now.date()
            
            if period == 'today':
                return queryset.filter(**{f'{date_field}__date': today})
            
            elif period == 'weekly':
                week_ago = now - timezone.timedelta(days=7)
                return queryset.filter(**{f'{date_field}__gte': week_ago})
            
            elif period == 'monthly':
                month_ago = now - timezone.timedelta(days=30)
                return queryset.filter(**{f'{date_field}__gte': month_ago})
            
            elif period == 'yearly':
                year_ago = now - timezone.timedelta(days=365)
                return queryset.filter(**{f'{date_field}__gte': year_ago})
            
            elif period == 'custom':
                start_date = filters.get('start_date')
                end_date = filters.get('end_date')
                if start_date and end_date:
                    return queryset.filter(
                        **{f'{date_field}__date__gte': start_date,
                           f'{date_field}__date__lte': end_date}
                    )
            
            return queryset
        except Exception as e:
            logger.error(f"Error applying date filter: {str(e)}")
            return queryset
    
    def _get_admin_dashboard_data(self, request, filters):
        """Full dashboard data for admin - with date filters"""
        try:
            # Base user queryset
            all_users_qs = User.objects.all()
            
            # Apply date filters to user creation
            filtered_users_qs = self._apply_date_filter(all_users_qs, filters, 'created_at')
            
            # Get admin/staff user IDs
            admin_staff_ids = StaffPermission.objects.filter(
                user_type__in=['admin', 'staff']
            ).values_list('user_id', flat=True)
            
            # Filtered regular users
            filtered_regular_users_qs = filtered_users_qs.exclude(id__in=admin_staff_ids)
            
            # ALL TIME totals (unfiltered) - for comparison
            total_users_all_time = all_users_qs.count()
            regular_users_all_time = all_users_qs.exclude(id__in=admin_staff_ids).count()
            admin_count_all_time = StaffPermission.objects.filter(user_type='admin').count()
            staff_count_all_time = StaffPermission.objects.filter(user_type='staff').count()
            
            # FILTERED counts (based on creation date)
            total_users_filtered = filtered_users_qs.count()
            regular_users_filtered = filtered_regular_users_qs.count()
            
            # Admin/Staff counts in filtered period (based on when they were created)
            admin_ids_in_period = StaffPermission.objects.filter(
                user_type='admin',
                user__in=filtered_users_qs
            ).values_list('user_id', flat=True)
            
            staff_ids_in_period = StaffPermission.objects.filter(
                user_type='staff',
                user__in=filtered_users_qs
            ).values_list('user_id', flat=True)
            
            admin_count_filtered = len(admin_ids_in_period)
            staff_count_filtered = len(staff_ids_in_period)
            
            # Active users in filtered period (based on last_login within period)
            active_users_qs = self._apply_date_filter(
                all_users_qs.filter(is_active=True),
                filters,
                'last_login'
            )
            
            active_users_filtered = active_users_qs.count()
            
            # Inactive users in filtered period
            if filters.get('period') != 'all':
                # Users created in period but never logged in OR last_login outside period
                users_created_in_period = filtered_users_qs
                users_active_in_period = active_users_qs
                inactive_users_filtered = users_created_in_period.exclude(
                    id__in=users_active_in_period.values_list('id', flat=True)
                ).count()
            else:
                # All-time inactive users
                inactive_users_filtered = all_users_qs.filter(is_active=False).count()
            
            # Regular users active/inactive breakdown
            active_regular_filtered = active_users_qs.exclude(id__in=admin_staff_ids).count()
            inactive_regular_filtered = regular_users_filtered - active_regular_filtered
            
            # Admin/Staff active/inactive counts in filtered period
            active_admin_filtered = StaffPermission.objects.filter(
                user_type='admin', 
                is_active=True,
                user__in=filtered_users_qs
            ).count()
            
            active_staff_filtered = StaffPermission.objects.filter(
                user_type='staff', 
                is_active=True,
                user__in=filtered_users_qs
            ).count()
            
            # Today and week counts (always based on filtered queryset)
            today = timezone.now().date()
            today_users = filtered_users_qs.filter(created_at__date=today).count()
            
            week_ago = timezone.now() - timezone.timedelta(days=7)
            week_users = filtered_users_qs.filter(created_at__gte=week_ago).count()
            
            # Get recent users from filtered queryset
            recent_users_data = []
            try:
                recent_users = filtered_users_qs.order_by('-created_at')[:10]
                recent_users_data = UserListSerializer(recent_users, many=True, context={'request': request}).data
            except Exception as e:
                logger.error(f"Error fetching recent users: {str(e)}")
            
            # Get period description
            period_desc = self._get_period_description(filters)
            
            stats_data = {
                # Filtered counts
                'total_users': total_users_filtered,
                'admin_count': admin_count_filtered,
                'staff_count': staff_count_filtered,
                'regular_users': regular_users_filtered,
                'active_users': active_users_filtered,
                'inactive_users': inactive_users_filtered,
                'today_new_users': today_users,
                'week_new_users': week_users,
                'recent_users': recent_users_data,
                'recent_users_count': len(recent_users_data),
                'timestamp': timezone.now(),
                'user_type': 'admin',
                'period': filters.get('period', 'all'),
                'period_description': period_desc,
                
                # All-time totals for comparison
                'all_time_totals': {
                    'total_users': total_users_all_time,
                    'admin_count': admin_count_all_time,
                    'staff_count': staff_count_all_time,
                    'regular_users': regular_users_all_time,
                },
                
                # Detailed breakdown
                'breakdown': {
                    'regular': {
                        'total': regular_users_filtered,
                        'active': active_regular_filtered,
                        'inactive': inactive_regular_filtered
                    },
                    'admin': {
                        'total': admin_count_filtered,
                        'active': active_admin_filtered,
                        'inactive': admin_count_filtered - active_admin_filtered
                    },
                    'staff': {
                        'total': staff_count_filtered,
                        'active': active_staff_filtered,
                        'inactive': staff_count_filtered - active_staff_filtered
                    }
                },
                
                
                # Filter info
                'filter_applied': {
                    'period': filters.get('period', 'all'),
                    'start_date': filters.get('start_date'),
                    'end_date': filters.get('end_date'),
                    'date_field': 'created_at'
                }
            }
            
            serializer = UserStatsSerializer(stats_data)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in _get_admin_dashboard_data: {str(e)}\n{traceback.format_exc()}")
            raise
    
    def _get_staff_dashboard_data(self, request, filters):
        """Limited dashboard data for staff - with date filters"""
        try:
            # Get IDs of admin and staff to exclude them
            admin_staff_ids = StaffPermission.objects.filter(
                user_type__in=['admin', 'staff']
            ).values_list('user_id', flat=True)
            
            # Base queryset for regular users
            regular_users_qs = User.objects.exclude(id__in=admin_staff_ids)
            
            # Apply date filters to user creation
            filtered_regular_users_qs = self._apply_date_filter(regular_users_qs, filters, 'created_at')
            
            # ALL TIME totals
            total_users_all_time = regular_users_qs.count()
            
            # FILTERED counts
            total_users_filtered = filtered_regular_users_qs.count()
            
            # Active users in filtered period
            active_users_qs = self._apply_date_filter(
                regular_users_qs.filter(last_login__isnull=False),
                filters,
                'last_login'
            )
            active_users_filtered = active_users_qs.count()
            
            # Inactive users in filtered period
            if filters.get('period') != 'all':
                users_created_in_period = filtered_regular_users_qs
                users_active_in_period = active_users_qs
                inactive_users_filtered = users_created_in_period.exclude(
                    id__in=users_active_in_period.values_list('id', flat=True)
                ).count()
            else:
                inactive_users_filtered = regular_users_qs.filter(is_active=False).count()
            
            # Staff sees fewer recent users
            recent_users_data = []
            try:
                recent_users = regular_users_qs.order_by('-created_at')[:5]
                
                for user_obj in recent_users:
                    user_data = {
                        'id': user_obj.id,
                        'mobile_number': user_obj.mobile_number,
                        'is_active': user_obj.is_active,
                        'created_at': user_obj.created_at,
                    }
                    if hasattr(user_obj, 'profile'):
                        try:
                            user_data['name'] = getattr(user_obj.profile, 'firstname', user_obj.mobile_number)
                        except:
                            user_data['name'] = user_obj.mobile_number
                    else:
                        user_data['name'] = user_obj.mobile_number
                    recent_users_data.append(user_data)
            except Exception as e:
                logger.error(f"Error fetching recent users for staff: {str(e)}")
            
            # Get period description
            period_desc = self._get_period_description(filters)
            
            stats_data = {
                'total_users': total_users_filtered,
                'regular_users': total_users_filtered,
                'active_users': active_users_filtered,
                'inactive_users': inactive_users_filtered,
                'today_new_users': self._get_today_count(regular_users_qs),
                'week_new_users': self._get_week_count(regular_users_qs),
                'active_last_month': self._get_monthly_active_count(regular_users_qs),
                'recent_users': recent_users_data,
                'timestamp': timezone.now(),
                'user_type': 'staff',
                'period': filters.get('period', 'all'),
                'period_description': period_desc,
                
                # All-time total for comparison
                'all_time_total_users': total_users_all_time,
                
                # Filter info
                'filter_applied': {
                    'period': filters.get('period', 'all'),
                    'start_date': filters.get('start_date'),
                    'end_date': filters.get('end_date')
                }
            }
            
            from .serializers import StaffDashboardStatsSerializer
            serializer = StaffDashboardStatsSerializer(stats_data)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in _get_staff_dashboard_data: {str(e)}\n{traceback.format_exc()}")
            raise
    
    def _get_period_description(self, filters):
        """Get human-readable period description"""
        try:
            period = filters.get('period', 'all')
            
            if period == 'all':
                return "All time"
            elif period == 'today':
                return "Today"
            elif period == 'weekly':
                return "Last 7 days"
            elif period == 'monthly':
                return "Last 30 days"
            elif period == 'yearly':
                return "Last 365 days"
            elif period == 'custom':
                start = filters.get('start_date')
                end = filters.get('end_date')
                return f"{start} to {end}"
            
            return period
        except Exception as e:
            logger.error(f"Error in _get_period_description: {str(e)}")
            return "Unknown period"
    
    def _get_today_count(self, queryset):
        """Get count of users created today"""
        try:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today).count()
        except Exception as e:
            logger.error(f"Error in _get_today_count: {str(e)}")
            return 0
    
    def _get_week_count(self, queryset):
        """Get count of users created in last 7 days"""
        try:
            week_ago = timezone.now() - timezone.timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago).count()
        except Exception as e:
            logger.error(f"Error in _get_week_count: {str(e)}")
            return 0
    
    def _get_monthly_active_count(self, queryset):
        """Get count of users active in last 30 days"""
        try:
            thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
            return queryset.filter(last_login__gte=thirty_days_ago).count()
        except Exception as e:
            logger.error(f"Error in _get_monthly_active_count: {str(e)}")
            return 0
        

# apps/admin_app/views.py (add this new ViewSet)

class ProfileOverrideViewSet(BaseModelViewSet):
    """ViewSet for managing unified profile overrides."""
    permission_classes = [IsAuthenticated]
    serializer_class = RelationProfileOverrideSerializer
    queryset = RelationProfileOverride.objects.all().order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ProfileOverrideCreateSerializer
        return RelationProfileOverrideSerializer
    
    def get_queryset(self):
        try:
            queryset = super().get_queryset()
            
            # Apply filters from query params
            search_serializer = ProfileOverrideSearchSerializer(data=self.request.query_params)
            if search_serializer.is_valid():
                filters = search_serializer.validated_data
                
                for field, value in filters.items():
                    if value and field not in ['from_date', 'to_date']:
                        queryset = queryset.filter(**{field: value})
                
                if filters.get('from_date'):
                    queryset = queryset.filter(created_at__date__gte=filters['from_date'])
                if filters.get('to_date'):
                    queryset = queryset.filter(created_at__date__lte=filters['to_date'])
                
            
            return queryset.select_related('relation')
            
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}")
            return RelationProfileOverride.objects.none()
    
    def _check_permission(self, user):
        """Check if user has permission to manage profile overrides."""
        try:
            if IsAdminUser().has_permission(self.request, self):
                return True
            
            try:
                relation_perm = RelationManagementPermission.objects.get(user=user)
                return relation_perm.can_manage_profile_overrides
            except RelationManagementPermission.DoesNotExist:
                return False
        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}")
            return False
    
    def create(self, request, *args, **kwargs):
        try:
            if not self._check_permission(request.user):
                return Response(
                    {'error': 'You do not have permission to create profile overrides'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            
            # Get the fixed relation
            try:
                relation = FixedRelation.objects.get(relation_code=data['relation_code'])
            except FixedRelation.DoesNotExist:
                return Response(
                    {'error': f"Relation {data['relation_code']} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Create the override INSIDE transaction
            with transaction.atomic():
                # Build unique together fields
                override_kwargs = {
                    'relation': relation,
                    'language': data.get('language', 'en'),
                    'lifestyle': data.get('lifestyle'),
                    'familyname8': data.get('familyname8'),
                    'family': data.get('family'),
                    'native': data.get('native'),
                    'present_city': data.get('present_city'),
                    'taluk': data.get('taluk'),
                    'district': data.get('district'),
                    'state': data.get('state'),
                    'nationality': data.get('nationality'),
                }
                
                # Remove None values
                override_kwargs = {k: v for k, v in override_kwargs.items() if v is not None}
                
                # Create or update the override
                override, created = RelationProfileOverride.objects.update_or_create(
                    **override_kwargs,
                    defaults={
                        'label': data['label']
                    }
                )
            
            # LOGGING OUTSIDE TRANSACTION - won't rollback if logging fails
            try:
                field_summary = self._get_field_summary(data)
                RelationAdminActivityLog.objects.create(
                    user=request.user,
                    action='profile_override_create' if created else 'profile_override_update',
                    description=f'{"Created" if created else "Updated"} profile override for {relation.relation_code}: {field_summary}',
                    relation_code=relation.relation_code,
                    affected_level='profile',
                    ip_address=self.get_client_ip(request),
                    metadata={
                        'fields': field_summary,
                        'label': data['label'],
                        'is_new': created,
                        'override_id': override.id
                    }
                )
            except Exception as e:
                # Log but don't fail the request
                logger.error(f"Error logging activity: {str(e)}", exc_info=True)
            
            response_serializer = RelationProfileOverrideSerializer(override)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
            
        except serializers.ValidationError as e:
            logger.error(f"Validation error: {str(e)}")
            return Response(
                {'errors': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except IntegrityError as e:
            logger.error(f"Integrity error creating override: {str(e)}")
            return Response(
                {'error': 'This exact override combination already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating override: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    def list(self, request, *args, **kwargs):
        if not self._check_permission(request.user):
            return Response(
                {'error': 'You do not have permission to view profile overrides'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if not self._check_permission(request.user):
            return Response(
                {'error': 'You do not have permission to view this profile override'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Get analytics for all overrides."""
        try:
            total_overrides = RelationProfileOverride.objects.count()
            
            # Count by field combinations
            by_level = {
                'with_lifestyle': RelationProfileOverride.objects.exclude(lifestyle__isnull=True).exclude(lifestyle='').count(),
                'with_familyname8': RelationProfileOverride.objects.exclude(familyname8__isnull=True).exclude(familyname8='').count(),
                'with_family': RelationProfileOverride.objects.exclude(family__isnull=True).exclude(family='').count(),
                'with_native': RelationProfileOverride.objects.exclude(native__isnull=True).exclude(native='').count(),
                'with_city': RelationProfileOverride.objects.exclude(present_city__isnull=True).exclude(present_city='').count(),
                'with_taluk': RelationProfileOverride.objects.exclude(taluk__isnull=True).exclude(taluk='').count(),
                'with_district': RelationProfileOverride.objects.exclude(district__isnull=True).exclude(district='').count(),
                'with_state': RelationProfileOverride.objects.exclude(state__isnull=True).exclude(state='').count(),
                'with_nationality': RelationProfileOverride.objects.exclude(nationality__isnull=True).exclude(nationality='').count(),
            }
            
            # Most overridden relations
            from django.db.models import Count
            by_relation = list(
                RelationProfileOverride.objects.values(
                    'relation__relation_code', 'relation__default_english'
                ).annotate(
                    count=Count('id')
                ).order_by('-count')[:10]
            )
            
            # Most specific overrides
            most_specific = []
            overrides = RelationProfileOverride.objects.all().order_by('-created_at')[:100]
            for override in overrides:
                score = override.get_specificity_score()
                if score >= 3:  # Only show highly specific ones
                    most_specific.append({
                        'id': override.id,
                        'relation_code': override.relation.relation_code,
                        'fields_used': score,
                        'fields': {
                            'lifestyle': override.lifestyle,
                            'familyname8': override.familyname8,
                            'family': override.family,
                            'native': override.native,
                            'city': override.present_city,
                            'district': override.district,
                            'state': override.state,
                        },
                        'label': override.label
                    })
            
            # Location coverage
            location_coverage = {
                'native_coverage': RelationProfileOverride.objects.exclude(native__isnull=True).exclude(native='').count(),
                'city_coverage': RelationProfileOverride.objects.exclude(present_city__isnull=True).exclude(present_city='').count(),
                'district_coverage': RelationProfileOverride.objects.exclude(district__isnull=True).exclude(district='').count(),
                'state_coverage': RelationProfileOverride.objects.exclude(state__isnull=True).exclude(state='').count(),
                'nationality_coverage': RelationProfileOverride.objects.exclude(nationality__isnull=True).exclude(nationality='').count(),
            }
            
            analytics_data = {
                'total_overrides': total_overrides,
                'by_level': by_level,
                'by_relation': by_relation[:5],
                'most_specific_overrides': most_specific[:5],
                'location_coverage': location_coverage
            }
            
            serializer = OverrideAnalyticsSerializer(analytics_data)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in analytics: {str(e)}")
            return Response(
                {'error': 'Failed to generate analytics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def search_by_profile(self, request):
        """Search for overrides matching a user's profile."""
        try:
            user_id = request.query_params.get('user_id')
            if not user_id:
                return Response(
                    {'error': 'user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from apps.profiles.models import UserProfile
            try:
                profile = UserProfile.objects.get(user_id=user_id)
            except UserProfile.DoesNotExist:
                return Response(
                    {'error': 'User profile not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Build query from profile fields
            query = Q()
            field_mapping = {
                'lifestyle': profile.lifestyle,
                'familyname8': profile.familyname8,
                'family': profile.familyname1,  # Adjust as needed
                'native': profile.native,
                'present_city': profile.present_city,
                'taluk': profile.taluk,
                'district': profile.district,
                'state': profile.state,
                'nationality': profile.nationality,
            }
            
            for field, value in field_mapping.items():
                if value:
                    query |= Q(**{field: value})
            
            matching_overrides = RelationProfileOverride.objects.filter(query).distinct()
            
            serializer = self.get_serializer(matching_overrides, many=True)
            return Response({
                'user_id': user_id,
                'total_matches': matching_overrides.count(),
                'overrides': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error in search_by_profile: {str(e)}")
            return Response(
                {'error': 'Failed to search by profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_field_summary(self, data):
        """Generate a summary of which fields are set in the override."""
        fields = []
        if data.get('lifestyle'): fields.append('lifestyle')
        if data.get('familyname8'): fields.append('familyname8')
        if data.get('family'): fields.append('family')
        if data.get('native'): fields.append('native')
        if data.get('present_city'): fields.append('city')
        if data.get('taluk'): fields.append('taluk')
        if data.get('district'): fields.append('district')
        if data.get('state'): fields.append('state')
        if data.get('nationality'): fields.append('nationality')
        
        return ', '.join(fields) if fields else 'basic'
    
    
# Add this to your admin_app/views.py file (after RelationAutoSuggestViewSet)

class UserEnteredAutoSuggestViewSet(BaseModelViewSet):
    """Auto-suggestion endpoints based on user-entered profile data."""
    permission_classes = [AllowAny]
    
    def _get_user_profile_model(self):
        """Get the UserProfile model dynamically."""
        from django.apps import apps
        try:
            return apps.get_model('profiles', 'UserProfile')
        except LookupError:
            logger.warning("UserProfile model not found in 'profiles' app")
            return None
    
    @action(detail=False, methods=['get'])
    def user_familyname8s(self, request):
        """Suggest familyname8 values based on what users have entered in their profiles."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                # Get distinct familyname8 values from user profiles (starts with)
                try:
                    # Use user_id or user as the count field instead of id
                    familyname8_results = UserProfile.objects.filter(
                        familyname8__isnull=False
                    ).exclude(
                        familyname8__exact=''
                    ).filter(
                        familyname8__istartswith=query
                    ).values('familyname8').annotate(
                        count=Count('user')  # Changed from 'id' to 'user'
                    ).order_by('-count', 'familyname8')[:limit]
                    
                    suggestions = [
                        {
                            'value': item['familyname8'],
                            'label': item['familyname8'],
                            'count': item['count'],
                            'source': 'user_entered'
                        }
                        for item in familyname8_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching user familyname8 suggestions (starts with): {str(e)}")
                
                # Fallback to contains if no results
                if not suggestions and len(query) >= 2:
                    try:
                        familyname8_results = UserProfile.objects.filter(
                            familyname8__isnull=False
                        ).exclude(
                            familyname8__exact=''
                        ).filter(
                            familyname8__icontains=query
                        ).values('familyname8').annotate(
                            count=Count('user')  # Changed from 'id' to 'user'
                        ).order_by('-count', 'familyname8')[:limit]
                        
                        suggestions = [
                            {
                                'value': item['familyname8'],
                                'label': item['familyname8'],
                                'count': item['count'],
                                'source': 'user_entered'
                            }
                            for item in familyname8_results
                        ]
                    except Exception as e:
                        logger.error(f"Error fetching user familyname8 suggestions (contains): {str(e)}")
            
            # Also get from RelationProfileOverride if available
            try:
                # For RelationProfileOverride, it likely has an 'id' field
                override_results = RelationProfileOverride.objects.filter(
                    familyname8__isnull=False
                ).exclude(
                    familyname8__exact=''
                ).filter(
                    familyname8__istartswith=query
                ).values('familyname8').annotate(
                    count=Count('id')  # This is fine for this model
                ).order_by('-count', 'familyname8')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['familyname8'] for s in suggestions):
                        suggestions.append({
                            'value': item['familyname8'],
                            'label': item['familyname8'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override familyname8 suggestions: {str(e)}")
            
            # Sort by count (highest first) then alphabetically
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_familyname8s: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_families(self, request):
        """Suggest family values based on what users have entered in their profiles."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                # Try different possible family field names
                family_fields = ['familyname1', 'family_name', 'family']
                
                for field in family_fields:
                    try:
                        filter_kwargs = {
                            f"{field}__isnull": False,
                            f"{field}__istartswith": query
                        }
                        
                        family_results = UserProfile.objects.filter(**filter_kwargs).exclude(
                        **{f"{field}__exact": ''}
                    ).values(field).annotate(
                        count=Count('id')
                    ).order_by('-count')[:limit]
                        
                        for result in family_results:
                            suggestions.append({
                                'value': result[field],
                                'label': result[field],
                                'count': result['count'],
                                'source': 'user_entered'
                            })
                        
                        if suggestions:
                            break
                    except (FieldError, AttributeError):
                        continue
            
            # Get from RelationProfileOverride
            try:
                override_results = RelationProfileOverride.objects.filter(
                    family__isnull=False
                ).exclude(
                    family__exact=''
                ).filter(
                    family__istartswith=query
                ).values('family').annotate(
                    count=Count('id')
                ).order_by('-count', 'family')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['family'] for s in suggestions):
                        suggestions.append({
                            'value': item['family'],
                            'label': item['family'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override family suggestions: {str(e)}")
            
            # Sort results
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_families: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_languages(self, request):
        """Suggest language values based on what users have entered."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                # Try different possible language fields
                language_fields = ['preferred_language', 'mother_tongue', 'language']
                
                for field in language_fields:
                    try:
                        filter_kwargs = {
                            f"{field}__isnull": False,
                            f"{field}__istartswith": query
                        }
                        
                        lang_results = UserProfile.objects.filter(**filter_kwargs).exclude(
                            **{f"{field}__exact": ''}
                        ).values(lang_value=field).annotate(
                            count=Count('id')
                        ).order_by('-count')[:limit]
                        
                        for result in lang_results:
                            suggestions.append({
                                'value': result['lang_value'],
                                'label': result['lang_value'],
                                'count': result['count'],
                                'source': 'user_entered'
                            })
                        
                        if suggestions:
                            break
                    except (FieldError, AttributeError):
                        continue
            
            # Get from RelationProfileOverride
            try:
                override_results = RelationProfileOverride.objects.filter(
                    language__isnull=False
                ).exclude(
                    language__exact=''
                ).filter(
                    language__istartswith=query
                ).values('language').annotate(
                    count=Count('id')
                ).order_by('-count', 'language')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['language'] for s in suggestions):
                        suggestions.append({
                            'value': item['language'],
                            'label': item['language'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override language suggestions: {str(e)}")
            
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_languages: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_lifestyles(self, request):
        """Suggest lifestyle values based on what users have entered."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                try:
                    lifestyle_results = UserProfile.objects.filter(
                        lifestyle__isnull=False
                    ).exclude(
                        lifestyle__exact=''
                    ).filter(
                        lifestyle__istartswith=query
                    ).values('lifestyle').annotate(
                        count=Count('id')
                    ).order_by('-count', 'lifestyle')[:limit]
                    
                    suggestions = [
                        {
                            'value': item['lifestyle'],
                            'label': item['lifestyle'],
                            'count': item['count'],
                            'source': 'user_entered'
                        }
                        for item in lifestyle_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching user lifestyle suggestions: {str(e)}")
            
            # Get from RelationProfileOverride
            try:
                override_results = RelationProfileOverride.objects.filter(
                    lifestyle__isnull=False
                ).exclude(
                    lifestyle__exact=''
                ).filter(
                    lifestyle__istartswith=query
                ).values('lifestyle').annotate(
                    count=Count('id')
                ).order_by('-count', 'lifestyle')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['lifestyle'] for s in suggestions):
                        suggestions.append({
                            'value': item['lifestyle'],
                            'label': item['lifestyle'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override lifestyle suggestions: {str(e)}")
            
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_lifestyles: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_natives(self, request):
        """Suggest native place values based on what users have entered."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                try:
                    native_results = UserProfile.objects.filter(
                        native__isnull=False
                    ).exclude(
                        native__exact=''
                    ).filter(
                        native__istartswith=query
                    ).values('native').annotate(
                        count=Count('id')
                    ).order_by('-count', 'native')[:limit]
                    
                    suggestions = [
                        {
                            'value': item['native'],
                            'label': item['native'],
                            'count': item['count'],
                            'source': 'user_entered'
                        }
                        for item in native_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching user native suggestions: {str(e)}")
            
            # Get from RelationProfileOverride
            try:
                override_results = RelationProfileOverride.objects.filter(
                    native__isnull=False
                ).exclude(
                    native__exact=''
                ).filter(
                    native__istartswith=query
                ).values('native').annotate(
                    count=Count('id')
                ).order_by('-count', 'native')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['native'] for s in suggestions):
                        suggestions.append({
                            'value': item['native'],
                            'label': item['native'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override native suggestions: {str(e)}")
            
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_natives: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_cities(self, request):
        """Suggest city values based on what users have entered."""
        try:
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 10)), 50)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            suggestions = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                # Try present_city field
                try:
                    city_results = UserProfile.objects.filter(
                        present_city__isnull=False
                    ).exclude(
                        present_city__exact=''
                    ).filter(
                        present_city__istartswith=query
                    ).values('present_city').annotate(
                        count=Count('id')
                    ).order_by('-count', 'present_city')[:limit]
                    
                    for item in city_results:
                        suggestions.append({
                            'value': item['present_city'],
                            'label': item['present_city'],
                            'count': item['count'],
                            'source': 'user_entered'
                        })
                except Exception as e:
                    logger.error(f"Error fetching user city suggestions: {str(e)}")
            
            # Get from RelationProfileOverride
            try:
                override_results = RelationProfileOverride.objects.filter(
                    present_city__isnull=False
                ).exclude(
                    present_city__exact=''
                ).filter(
                    present_city__istartswith=query
                ).values('present_city').annotate(
                    count=Count('id')
                ).order_by('-count', 'present_city')[:limit]
                
                for item in override_results:
                    if not any(s['value'] == item['present_city'] for s in suggestions):
                        suggestions.append({
                            'value': item['present_city'],
                            'label': item['present_city'],
                            'count': item['count'],
                            'source': 'override'
                        })
            except Exception as e:
                logger.error(f"Error fetching override city suggestions: {str(e)}")
            
            suggestions.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': suggestions[:limit],
                'type': 'user_entered'
            })
            
        except Exception as e:
            logger.error(f"Error in user_cities: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def combined_suggestions(self, request):
        """Get combined suggestions from both admin and user data."""
        try:
            field = request.query_params.get('field', 'familyname8')
            query = request.query_params.get('q', '').strip().lower()
            limit = min(int(request.query_params.get('limit', 20)), 100)
            
            if len(query) < 2:
                return Response({'suggestions': []})
            
            admin_suggestions = []
            user_suggestions = []
            
            # Get admin suggestions (from existing RelationAutoSuggestViewSet methods)
            if field == 'familyname8':
                try:
                    familyname8_results = Relationfamilyname8.objects.filter(
                        familyname8__istartswith=query
                    ).values('familyname8').annotate(
                        count=Count('id')
                    ).order_by('-count', 'familyname8')[:limit//2]
                    
                    admin_suggestions = [
                        {
                            'value': item['familyname8'],
                            'label': item['familyname8'],
                            'count': item['count'],
                            'source': 'admin'
                        }
                        for item in familyname8_results
                    ]
                except Exception as e:
                    logger.error(f"Error fetching admin familyname8 suggestions: {str(e)}")
            
            # Get user suggestions
            if field == 'familyname8':
                UserProfile = self._get_user_profile_model()
                if UserProfile:
                    try:
                        user_results = UserProfile.objects.filter(
                            familyname8__isnull=False
                        ).exclude(
                            familyname8__exact=''
                        ).filter(
                            familyname8__istartswith=query
                        ).values('familyname8').annotate(
                            count=Count('id')
                        ).order_by('-count', 'familyname8')[:limit//2]
                        
                        user_suggestions = [
                            {
                                'value': item['familyname8'],
                                'label': item['familyname8'],
                                'count': item['count'],
                                'source': 'user'
                            }
                            for item in user_results
                        ]
                    except Exception as e:
                        logger.error(f"Error fetching user familyname8 suggestions: {str(e)}")
            
            # Merge and sort
            all_suggestions = admin_suggestions + user_suggestions
            
            # Remove duplicates (keep the one with higher count)
            unique_suggestions = {}
            for s in all_suggestions:
                if s['value'] not in unique_suggestions or s['count'] > unique_suggestions[s['value']]['count']:
                    unique_suggestions[s['value']] = s
            
            result = list(unique_suggestions.values())
            result.sort(key=lambda x: (-x['count'], x['value']))
            
            return Response({
                'query': query,
                'suggestions': result[:limit],
                'type': 'combined',
                'stats': {
                    'admin_count': len(admin_suggestions),
                    'user_count': len(user_suggestions),
                    'total': len(result)
                }
            })
            
        except Exception as e:
            logger.error(f"Error in combined_suggestions: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get suggestions. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def popular_values(self, request):
        """Get most popular values entered by users."""
        try:
            field = request.query_params.get('field', 'familyname8')
            limit = min(int(request.query_params.get('limit', 20)), 50)
            
            popular = []
            UserProfile = self._get_user_profile_model()
            
            if UserProfile:
                field_mapping = {
                    'familyname8': 'familyname8',
                    'lifestyle': 'lifestyle',
                    'language': 'preferred_language',
                    'city': 'present_city',
                    'native': 'native'
                }
                
                profile_field = field_mapping.get(field)
                if profile_field:
                    try:
                        results = UserProfile.objects.filter(
                            **{f"{profile_field}__isnull": False}
                        ).exclude(
                            **{f"{profile_field}__exact": ''}
                        ).values(value=profile_field).annotate(
                            count=Count('id')
                        ).order_by('-count')[:limit]
                        
                        popular = [
                            {
                                'value': item['value'],
                                'label': item['value'],
                                'count': item['count'],
                                'source': 'user'
                            }
                            for item in results
                        ]
                    except Exception as e:
                        logger.error(f"Error fetching popular values for {field}: {str(e)}")
            
            return Response({
                'field': field,
                'suggestions': popular,
                'type': 'popular'
            })
            
        except Exception as e:
            logger.error(f"Error in popular_values: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Failed to get popular values. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
# Add to your views.py

class PermissionListView(BaseAPIView):
    """List all available permissions in the system"""
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        """Return all permission definitions"""
        permissions = {
            'staff_permissions': [
                {'id': 'can_view_dashboard', 'name': 'View Dashboard', 'group': 'Dashboard'},
                {'id': 'can_manage_dashboard', 'name': 'Manage Dashboard', 'group': 'Dashboard'},
                {'id': 'can_view_users', 'name': 'View Users', 'group': 'User Management'},
                {'id': 'can_edit_users', 'name': 'Edit Users', 'group': 'User Management'},
                {'id': 'can_export_data', 'name': 'Export Data', 'group': 'Data'},
            ],
            'relation_permissions': [
                {'id': 'can_manage_fixed_relations', 'name': 'Manage Fixed Relations', 'group': 'Relations'},
                {'id': 'can_manage_language_lifestyle', 'name': 'Manage Language/lifestyle Overrides', 'group': 'Relations'},
                {'id': 'can_manage_familyname8_overrides', 'name': 'Manage familyname8 Overrides', 'group': 'Relations'},
                {'id': 'can_manage_family_overrides', 'name': 'Manage Family Overrides', 'group': 'Relations'},
                {'id': 'can_manage_profile_overrides', 'name': 'Manage Profile Overrides', 'group': 'Relations'},
                {'id': 'can_view_relation_analytics', 'name': 'View Relation Analytics', 'group': 'Analytics'},
            ],
            'other_permissions':[
                {'id': 'can_manage_chat', 'name': 'Manage Chat', 'group': 'Chat'},
                {'id': 'can_manage_post', 'name': 'Manage Posts', 'group': 'Content'},
            ]
        }
        return Response(permissions)


class CurrentUserPermissionsView(BaseAPIView):
    """Get current user's permissions"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        permissions = {
            'is_admin': False,
            'is_staff': False,
            'user_type': 'regular',
            'permissions': {}
        }
        
        try:
            staff_perm = StaffPermission.objects.get(user=user)
            permissions['is_staff'] = True
            permissions['user_type'] = staff_perm.user_type
            permissions['is_admin'] = (staff_perm.user_type == 'admin')
            
            # Staff permissions
            permissions['permissions']['staff'] = {
                'can_view_dashboard': staff_perm.can_view_dashboard,
                'can_manage_dashboard': staff_perm.can_manage_dashboard,
                'can_view_users': staff_perm.can_view_users,
                'can_edit_users': staff_perm.can_edit_users,
                'can_export_data': staff_perm.can_export_data,
                'can_manage_chat': staff_perm.can_manage_chat,
                'can_manage_post': staff_perm.can_manage_post,
            }
        except StaffPermission.DoesNotExist:
            pass
        
        try:
            relation_perm = RelationManagementPermission.objects.get(user=user)
            permissions['permissions']['relations'] = {
                'can_manage_fixed_relations': relation_perm.can_manage_fixed_relations,
                'can_manage_language_lifestyle': relation_perm.can_manage_language_lifestyle,
                'can_manage_familyname8_overrides': relation_perm.can_manage_familyname8_overrides,
                'can_manage_family_overrides': relation_perm.can_manage_family_overrides,
                'can_manage_profile_overrides': relation_perm.can_manage_profile_overrides,
                'can_view_relation_analytics': relation_perm.can_view_relation_analytics,
            }
        except RelationManagementPermission.DoesNotExist:
            pass
        
        return Response(permissions)


class StaffPermissionUpdateView(BaseAPIView):
    """Update permissions for a staff user"""
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def put(self, request, staff_id):
        try:
            staff_user = User.objects.get(id=staff_id)
            
            try:
                staff_perm = StaffPermission.objects.get(user=staff_user)
            except StaffPermission.DoesNotExist:
                return Response(
                    {'error': 'Staff permissions not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update staff permissions
            for field in ['can_view_dashboard', 'can_manage_dashboard', 
                         'can_view_users', 'can_edit_users', 'can_export_data']:
                if field in request.data:
                    setattr(staff_perm, field, request.data[field])
            
            staff_perm.save()
            
            # Also update relation permissions if provided
            if 'relation_permissions' in request.data:
                relation_perm, created = RelationManagementPermission.objects.get_or_create(
                    user=staff_user
                )
                for field in ['can_manage_fixed_relations', 'can_manage_language_lifestyle',
                             'can_manage_familyname8_overrides', 'can_manage_family_overrides',
                             'can_manage_profile_overrides', 'can_view_relation_analytics']:
                    if field in request.data['relation_permissions']:
                        setattr(relation_perm, field, request.data['relation_permissions'][field])
                relation_perm.save()
            
            # Log activity
            AdminActivityLog.objects.create(
                user=request.user,
                action='permission_update',
                description=f'Updated permissions for staff {staff_user.mobile_number}',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({'success': True, 'message': 'Permissions updated successfully'})
            
        except User.DoesNotExist:
            return Response({'error': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating permissions: {str(e)}")
            return Response({'error': 'Failed to update permissions'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            

class StaffPermissionsManageView(BaseAPIView):
    """
    Dedicated endpoint for managing staff permissions
    Admin only - separate from profile updates
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, staff_id):
        """Get staff member's current permissions"""
        try:
            staff_user = User.objects.get(id=staff_id)
            
            # Check if user is actually staff
            try:
                staff_perm = StaffPermission.objects.get(user=staff_user)
                if staff_perm.user_type != 'staff':
                    return Response(
                        {'error': 'User is not a staff member'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except StaffPermission.DoesNotExist:
                return Response(
                    {'error': 'Staff permissions not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get admin profile for display
            admin_profile = AdminProfile.objects.get(user=staff_user)
            
            # Get relation permissions if they exist
            relation_perm = None
            try:
                relation_perm = RelationManagementPermission.objects.get(user=staff_user)
            except RelationManagementPermission.DoesNotExist:
                pass
            
            return Response({
                'staff_id': staff_user.id,
                'name': admin_profile.full_name,
                'mobile': staff_user.mobile_number,
                'email': admin_profile.email,
                'permissions': {
                    # Staff permissions
                    'can_view_dashboard': staff_perm.can_view_dashboard,
                    'can_manage_dashboard': staff_perm.can_manage_dashboard,
                    'can_view_users': staff_perm.can_view_users,
                    'can_edit_users': staff_perm.can_edit_users,
                    'can_export_data': staff_perm.can_export_data,
                    
                    # Relation permissions (if they exist)
                    'can_manage_fixed_relations': relation_perm.can_manage_fixed_relations if relation_perm else False,
                    'can_manage_language_lifestyle': relation_perm.can_manage_language_lifestyle if relation_perm else False,
                    'can_manage_familyname8_overrides': relation_perm.can_manage_familyname8_overrides if relation_perm else False,
                    'can_manage_family_overrides': relation_perm.can_manage_family_overrides if relation_perm else False,
                    'can_manage_profile_overrides': relation_perm.can_manage_profile_overrides if relation_perm else False,
                    'can_view_relation_analytics': relation_perm.can_view_relation_analytics if relation_perm else False,
                    'can_manage_chat': staff_perm.can_manage_chat,
                    'can_manage_post': staff_perm.can_manage_post,
                    'can_manage_event': staff_perm.can_manage_event, 
                }
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'Staff not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except AdminProfile.DoesNotExist:
            return Response(
                {'error': 'Staff profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error fetching staff permissions: {str(e)}")
            return Response(
                {'error': 'Failed to fetch permissions'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request, staff_id):
        """Update staff permissions"""
        try:
            staff_user = User.objects.get(id=staff_id)
            
            # Check if user is actually staff
            try:
                staff_perm = StaffPermission.objects.get(user=staff_user)
                if staff_perm.user_type != 'staff':
                    return Response(
                        {'error': 'User is not a staff member'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except StaffPermission.DoesNotExist:
                return Response(
                    {'error': 'Staff permissions not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update staff permissions
            staff_fields = ['can_view_dashboard', 'can_manage_dashboard', 'can_manage_chat', 'can_manage_post',
                           'can_view_users', 'can_edit_users', 'can_export_data','can_manage_event']
            
            updated_fields = []
            for field in staff_fields:
                if field in request.data:
                    setattr(staff_perm, field, request.data[field])
                    updated_fields.append(field)
            
            staff_perm.save()
            
            # Update relation permissions if provided
            relation_fields = ['can_manage_fixed_relations', 'can_manage_language_lifestyle',
                              'can_manage_familyname8_overrides', 'can_manage_family_overrides',
                              'can_manage_profile_overrides', 'can_view_relation_analytics']
            
            relation_fields_in_request = [f for f in relation_fields if f in request.data]
            
            if relation_fields_in_request:
                relation_perm, created = RelationManagementPermission.objects.get_or_create(
                    user=staff_user
                )
                
                for field in relation_fields_in_request:
                    setattr(relation_perm, field, request.data[field])
                    updated_fields.append(field)
                
                relation_perm.save()
            
            # Log activity
            admin_profile = AdminProfile.objects.get(user=staff_user)
            AdminActivityLog.objects.create(
                user=request.user,
                action='permission_update',
                description=f'Updated permissions for staff: {admin_profile.full_name}',
                ip_address=self.get_client_ip(request),
                metadata={'updated_fields': updated_fields}
            )
            
            return Response({
                'success': True,
                'message': 'Permissions updated successfully',
                'updated_fields': updated_fields
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'Staff not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error updating staff permissions: {str(e)}")
            return Response(
                {'error': 'Failed to update permissions'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PermissionTemplatesView(BaseAPIView):
    """Get predefined permission templates/roles"""
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        templates = {
            'viewer': {
                'name': 'Viewer',
                'description': 'Can only view data, no edits',
                'permissions': {
                    'can_view_dashboard': True,
                    'can_manage_dashboard': False,
                    'can_view_users': True,
                    'can_edit_users': False,
                    'can_export_data': True,
                    'can_manage_fixed_relations': False,
                    'can_manage_language_lifestyle': False,
                    'can_manage_familyname8_overrides': False,
                    'can_manage_family_overrides': False,
                    'can_manage_profile_overrides': False,
                    'can_view_relation_analytics': True,
                }
            },
            'editor': {
                'name': 'Editor',
                'description': 'Can edit user data but not manage staff',
                'permissions': {
                    'can_view_dashboard': True,
                    'can_manage_dashboard': False,
                    'can_view_users': True,
                    'can_edit_users': True,
                    'can_export_data': True,
                    'can_manage_fixed_relations': False,
                    'can_manage_language_lifestyle': True,
                    'can_manage_familyname8_overrides': True,
                    'can_manage_family_overrides': True,
                    'can_manage_profile_overrides': True,
                    'can_view_relation_analytics': True,
                }
            },
            'manager': {
                'name': 'Manager',
                'description': 'Full access except staff management',
                'permissions': {
                    'can_view_dashboard': True,
                    'can_manage_dashboard': True,
                    'can_view_users': True,
                    'can_edit_users': True,
                    'can_export_data': True,
                    'can_manage_fixed_relations': True,
                    'can_manage_language_lifestyle': True,
                    'can_manage_familyname8_overrides': True,
                    'can_manage_family_overrides': True,
                    'can_manage_profile_overrides': True,
                    'can_view_relation_analytics': True,
                }
            }
        }
        return Response(templates)

class AdminActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing admin/staff activity logs.
    Read-only – logs are created automatically by the system.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminActivityLogSerializer
    queryset = AdminActivityLog.objects.all().order_by('-created_at')

    def get_queryset(self):
        queryset = super().get_queryset()
        # Optional filters
        user_id = self.request.query_params.get('user_id')
        action = self.request.query_params.get('action')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if action:
            queryset = queryset.filter(action=action)
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        return queryset.select_related('user', 'user__admin_profile')

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get overall summary of admin/staff activities.
        Returns counts by action type, top users, and recent activity.
        """
        today = timezone.now().date()
        week_ago = today - timezone.timedelta(days=7)
        month_ago = today - timezone.timedelta(days=30)

        logs = self.get_queryset()  # respects any query filters

        summary = {
            'total_logs': logs.count(),
            'today': logs.filter(created_at__date=today).count(),
            'this_week': logs.filter(created_at__date__gte=week_ago).count(),
            'this_month': logs.filter(created_at__date__gte=month_ago).count(),
            'by_action': {},
            'by_user_type': {
                'admin': logs.filter(user__staff_permissions__user_type='admin').count(),
                'staff': logs.filter(user__staff_permissions__user_type='staff').count(),
            },
            'top_users': [],
            'recent_actions': []
        }

        # Count by action (login, logout, create, update, delete, etc.)
        action_counts = logs.values('action').annotate(count=Count('id')).order_by('-count')
        for item in action_counts:
            summary['by_action'][item['action']] = item['count']

        # Top 5 users by activity count
        top_users = logs.values(
            'user__mobile_number',
            'user__admin_profile__full_name',
            'user__staff_permissions__user_type'
        ).annotate(activity_count=Count('id')).order_by('-activity_count')[:5]
        for user in top_users:
            summary['top_users'].append({
                'mobile_number': user['user__mobile_number'],
                'full_name': user['user__admin_profile__full_name'],
                'user_type': user['user__staff_permissions__user_type'],
                'activity_count': user['activity_count']
            })

        # Last 10 actions
        recent = logs.order_by('-created_at')[:10]
        summary['recent_actions'] = AdminActivityLogSerializer(recent, many=True, context={'request': request}).data

        return Response(summary)