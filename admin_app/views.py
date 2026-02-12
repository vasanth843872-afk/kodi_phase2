from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Q, Count
from .serializers import *

User = get_user_model()

from .models import StaffPermission, AdminActivityLog, AdminProfile
from .serializers import (
    AdminLoginSerializer, AdminRegistrationSerializer, StaffCreateSerializer,
    AdminProfileSerializer, AdminUpdateProfileSerializer,
    UserListSerializer,UserStatsSerializer
)
from .permissions import IsAdminUser, IsStaffUser, CanViewUsers

class AdminLoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Get admin profile (contains email)
            admin_profile = AdminProfile.objects.get(user=user)
            
            # Get staff permissions
            staff_perm = StaffPermission.objects.get(user=user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Prepare user data
            user_data = {
                'id': user.id,
                'mobile_number': user.mobile_number,
                'email': admin_profile.email,  # Get email from AdminProfile
                'full_name': admin_profile.full_name,
                'admin_id': admin_profile.admin_id,
                'user_type': staff_perm.user_type,
                'is_active': staff_perm.is_active,
                'department': admin_profile.department,
                'designation': admin_profile.designation,
                'phone': admin_profile.phone,
                'profile_picture': request.build_absolute_uri(
                    admin_profile.profile_picture.url
                ) if admin_profile.profile_picture else None,
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
            AdminActivityLog.objects.create(
                user=user,
                action='login',
                description=f'Admin {admin_profile.full_name} logged in',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'success': True,
                'message': 'Login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': user_data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class CreateInitialAdminView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Check if admin already exists
        if StaffPermission.objects.filter(user_type='admin').exists():
            return Response(
                {'error': 'Admin already exists'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AdminRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            admin_user = serializer.save()
            
            # Get admin profile (contains email)
            admin_profile = AdminProfile.objects.get(user=admin_user)
            
            return Response({
                'success': True,
                'message': 'Initial admin created successfully',
                'admin': {
                    'full_name': admin_profile.full_name,
                    'mobile_number': admin_user.mobile_number,
                    'email': admin_profile.email,  # Get email from AdminProfile
                    'admin_id': admin_profile.admin_id
                },
                'login_instructions': 'Use the same credentials to login'
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminProfileView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        user = request.user
        
        try:
            admin_profile = AdminProfile.objects.get(user=user)
            staff_perm = StaffPermission.objects.get(user=user)
        except:
            return Response(
                {'error': 'Admin profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        profile_data = {
            'full_name': admin_profile.full_name,
            'mobile_number': user.mobile_number,
            'email': admin_profile.email,  # Get email from AdminProfile
            'admin_id': admin_profile.admin_id,
            'phone': admin_profile.phone,
            'department': admin_profile.department,
            'designation': admin_profile.designation,
            'profile_picture': request.build_absolute_uri(
                admin_profile.profile_picture.url
            ) if admin_profile.profile_picture else None,
            'user_type': staff_perm.user_type,
            'is_active': staff_perm.is_active,
            'created_at': user.created_at,
            'last_login': user.last_login
        }
        
        return Response(profile_data)
    
    def put(self, request):
        user = request.user
        
        try:
            admin_profile = AdminProfile.objects.get(user=user)
        except:
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
            
            # Update admin profile fields
            full_name = serializer.validated_data.get('full_name')
            if full_name:
                admin_profile.full_name = full_name
                updated_fields.append('full_name')
            
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
            AdminActivityLog.objects.create(
                user=user,
                action='update',
                description='Updated admin profile',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'updated_fields': updated_fields
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
    
class AdminChangePasswordView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request):
        """Change admin password"""
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
            
            # Password validation
            if len(new_password) < 8:
                return Response(
                    {'error': 'Password must be at least 8 characters long'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if new password is same as old
            if new_password == old_password:
                return Response(
                    {'error': 'New password must be different from current password'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Set new password
            user.set_password(new_password)
            user.save()
            
            # Log activity
            AdminActivityLog.objects.create(
                user=user,
                action='password_change',
                description='Admin changed password',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class StaffManagementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]
    # serializer_class = StaffCreateSerializer
    queryset = User.objects.filter(staff_permissions__user_type='staff')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'retrieve':
            return StaffDetailSerializer
        elif self.action in ['create']:
            return StaffCreateSerializer   # ← Use this for POST
        elif self.action in ['update', 'partial_update']:
            return StaffUpdateSerializer
        return StaffCreateSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in ['retrieve', 'update', 'partial_update']:
            context['user'] = self.get_object()
        return context
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # ✅ Filter by is_active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() == 'true':
                queryset = queryset.filter(staff_permissions__is_active=True)
            elif is_active.lower() == 'false':
                queryset = queryset.filter(staff_permissions__is_active=False)
        
        # ✅ Alternative: filter by status parameter
        status = self.request.query_params.get('status')
        if status:
            if status.lower() == 'active':
                queryset = queryset.filter(staff_permissions__is_active=True)
            elif status.lower() == 'inactive':
                queryset = queryset.filter(staff_permissions__is_active=False)
        
        # ✅ Search functionality
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(mobile_number__icontains=search) |
                Q(admin_profile__full_name__icontains=search) |
                Q(admin_profile__email__icontains=search)
            )
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        staff_user = serializer.save()
        
        # Get admin profile (contains email)
        admin_profile = AdminProfile.objects.get(user=staff_user)
        
        AdminActivityLog.objects.create(
            user=request.user,
            action='create',
            description=f'Created staff: {admin_profile.full_name}',
            ip_address=self.get_client_ip(request)
        )
        
        return Response({
            'success': True,
            'message': 'Staff created',
            'staff': {
                'full_name': admin_profile.full_name,
                'mobile_number': staff_user.mobile_number,
                'email': admin_profile.email,  # Get email from AdminProfile, not User
                'admin_id': admin_profile.admin_id,
                'user_type': 'staff'
            }
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        staff_user = self.get_object()
        
        try:
            staff_perm = StaffPermission.objects.get(user=staff_user)
            staff_perm.is_active = not staff_perm.is_active
            staff_perm.save()
            
            # Get admin profile for logging
            admin_profile = AdminProfile.objects.get(user=staff_user)
            
            AdminActivityLog.objects.create(
                user=request.user,
                action='status_change',
                description=f'Changed status for staff {admin_profile.full_name}',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({
                'success': True,
                'message': f'Staff {"activated" if staff_perm.is_active else "deactivated"}',
                'staff': {
                    'full_name': admin_profile.full_name,
                    'mobile_number': staff_user.mobile_number,
                    'email': admin_profile.email,
                    'is_active': staff_perm.is_active
                }
            })
        except:
            return Response({'error': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated]  # Remove IsAdminUser
    
    def get(self, request):
        user = request.user
        
        try:
            staff_perm = StaffPermission.objects.get(user=user)
            
            # CASE 1: ADMIN - Full access, sees all counts
            if staff_perm.user_type == 'admin':
                return self._get_admin_dashboard_data(request)
            
            # CASE 2: STAFF - Only if they have permission
            elif staff_perm.user_type == 'staff':
                # Check if staff has permission to view dashboard
                if not staff_perm.can_view_dashboard:
                    return Response(
                        {'error': 'You do not have permission to view dashboard'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                # Staff dashboard - NO staff count, NO admin count
                return self._get_staff_dashboard_data(request)
            
            else:
                return Response(
                    {'error': 'Invalid user type'},
                    status=status.HTTP_403_FORBIDDEN
                )
                
        except StaffPermission.DoesNotExist:
            return Response(
                {'error': 'Permission not found'},
                status=status.HTTP_403_FORBIDDEN
            )
    
    def _get_admin_dashboard_data(self, request):
        """Full dashboard data for admin - includes staff count"""
        total_users = User.objects.count()
        admin_count = StaffPermission.objects.filter(user_type='admin', is_active=True).count()
        staff_count = StaffPermission.objects.filter(user_type='staff', is_active=True).count()
        regular_users = total_users - admin_count - staff_count
        
        today = timezone.now().date()
        today_users = User.objects.filter(created_at__date=today).count()
        
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        active_users = User.objects.filter(last_login__gte=thirty_days_ago).count()
        
        week_ago = timezone.now() - timezone.timedelta(days=7)
        week_users = User.objects.filter(created_at__gte=week_ago).count()
        
        recent_users = User.objects.order_by('-created_at')[:10]
        recent_users_data = UserListSerializer(recent_users, many=True).data
        
        stats_data = {
            'total_users': total_users,
            'admin_count': admin_count,
            'staff_count': staff_count,  # ✅ Staff count visible to admin only
            'regular_users': regular_users,
            'active_users': active_users,
            'today_new_users': today_users,
            'week_new_users': week_users,
            'recent_users': recent_users_data,
            'recent_users_count': len(recent_users_data),
            'timestamp': timezone.now(),
            'user_type': 'admin'
        }
        
        serializer = UserStatsSerializer(stats_data)
        return Response(serializer.data)
    
    def _get_staff_dashboard_data(self, request):
        """Limited dashboard data for staff - NO staff count, NO admin count"""
        # Get IDs of admin and staff to exclude them from regular users count
        admin_staff_ids = StaffPermission.objects.filter(
            user_type__in=['admin', 'staff']
        ).values_list('user_id', flat=True)
        
        # Only regular users (not admin/staff)
        regular_users = User.objects.exclude(id__in=admin_staff_ids)
        
        # Staff should only see regular users data
        total_users = regular_users.count()
        active_users = regular_users.filter(is_active=True).count()
        
        today = timezone.now().date()
        today_users = regular_users.filter(created_at__date=today).count()
        
        week_ago = timezone.now() - timezone.timedelta(days=7)
        week_users = regular_users.filter(created_at__gte=week_ago).count()
        
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        active_last_month = regular_users.filter(last_login__gte=thirty_days_ago).count()
        
        # Staff sees fewer recent users
        recent_users = regular_users.order_by('-created_at')[:5]
        recent_users_data = []
        
        for user_obj in recent_users:
            user_data = {
                'id': user_obj.id,
                'mobile_number': user_obj.mobile_number,
                'is_active': user_obj.is_active,
                'created_at': user_obj.created_at,
            }
            # Add name if available
            if hasattr(user_obj, 'profile'):
                user_data['name'] = getattr(user_obj.profile, 'firstname', user_obj.mobile_number)
            else:
                user_data['name'] = user_obj.mobile_number
            
            recent_users_data.append(user_data)
        
        stats_data = {
            'total_users': total_users,  # Only regular users
            'regular_users': total_users,  # For consistency
            'active_users': active_users,
            'today_new_users': today_users,
            'week_new_users': week_users,
            'active_last_month': active_last_month,
            'recent_users': recent_users_data,
            'timestamp': timezone.now(),
            'user_type': 'staff',
            # ❌ NO staff_count field at all
            # ❌ NO admin_count field at all
        }
        from .serializers import StaffDashboardStatsSerializer
        serializer = StaffDashboardStatsSerializer(stats_data)
        return Response(serializer.data)
        
        
class UserManagementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, CanViewUsers]
    serializer_class = UserListSerializer
    
    def get_queryset(self):
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
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        admin_staff_ids = StaffPermission.objects.filter(
            user_type__in=['admin', 'staff']
        ).values_list('user_id', flat=True)
        
        regular_users = User.objects.exclude(id__in=admin_staff_ids)
        
        total_users = regular_users.count()
        active_users = regular_users.filter(is_active=True).count()
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
            'week_new_users': week_users,
            'timestamp': timezone.now()
        }
        
        serializer = UserStatsSerializer(stats_data)
        return Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        """Get single user with basic info"""
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
    
    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        """Get user's full profile details (admin view)"""
        user = self.get_object()
        
        # Check if user is admin/staff (should be excluded)
        try:
            StaffPermission.objects.get(user=user)
            return Response(
                {'error': 'Cannot view admin/staff profiles from this endpoint'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except StaffPermission.DoesNotExist:
            pass
        
        # Get or create user profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Use PrivateProfileSerializer for admin view (shows all fields)
        serializer = PrivateProfileSerializer(
            profile, 
            context={'request': request}
        )
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def profile_completion(self, request, pk=None):
        """Get user's profile completion status"""
        user = self.get_object()
        
        # Check if user is admin/staff
        try:
            StaffPermission.objects.get(user=user)
            return Response(
                {'error': 'Cannot view admin/staff profiles from this endpoint'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except StaffPermission.DoesNotExist:
            pass
        
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Define required fields for each step (same as in ProfileCompletionStatusView)
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
            total = len(fields)
            completed = sum(1 for field in fields if getattr(profile, field))
            return (completed / total * 100) if total > 0 else 0
        
        completion = {
            'user_id': user.id,
            'mobile_number': user.mobile_number,
            'step1_percentage': calculate_completion(step1_fields),
            'step2_percentage': calculate_completion(step2_fields),
            'step3_percentage': calculate_completion(step3_fields),
            'total_percentage': calculate_completion(step1_fields + step2_fields + step3_fields),
            'is_complete': all([
                calculate_completion(step1_fields) == 100,
                calculate_completion(step2_fields) == 100,
                calculate_completion(step3_fields) == 100
            ]),
            'created_at': profile.created_at,
            'updated_at': profile.updated_at
        }
        
        return Response(completion)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        if not self._is_admin():
            return Response({'error': 'Only admin can deactivate'}, status=status.HTTP_403_FORBIDDEN)
        
        user = self.get_object()
        
        try:
            StaffPermission.objects.get(user=user)
            return Response({'error': 'Cannot deactivate admin/staff'}, status=status.HTTP_400_BAD_REQUEST)
        except:
            pass
        
        user.is_active = False
        user.save()
        
        AdminActivityLog.objects.create(
            user=request.user,
            action='status_change',
            description=f'Deactivated user {user.mobile_number}',
            ip_address=self.get_client_ip(request)
        )
        
        return Response({'success': True, 'message': 'User deactivated'})
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        if not self._is_admin():
            return Response({'error': 'Only admin can activate'}, status=status.HTTP_403_FORBIDDEN)
        
        user = self.get_object()
        user.is_active = True
        user.save()
        
        AdminActivityLog.objects.create(
            user=request.user,
            action='status_change',
            description=f'Activated user {user.mobile_number}',
            ip_address=self.get_client_ip(request)
        )
        
        return Response({'success': True, 'message': 'User activated'})
    
    def _is_admin(self):
        try:
            staff_perm = StaffPermission.objects.get(user=self.request.user)
            return staff_perm.user_type == 'admin'
        except:
            return False
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


# admin_app/views.py (add to your existing file)
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from django.db import transaction

from .models import (
    RelationManagementPermission, 
    RelationAdminActivityLog,
    StaffPermission
)
from .serializers import (
    RelationManagementPermissionSerializer,
    RelationAdminActivityLogSerializer,
    FixedRelationSerializer,
    LanguageReligionOverrideSerializer,
    CasteOverrideSerializer,
    FamilyOverrideSerializer,
    BulkOverrideSerializer,
    RelationLabelTestSerializer,
    RelationAnalyticsSerializer
)
from .permissions import IsAdminUser, IsStaffUser
from apps.relations.models import (
    FixedRelation, 
    RelationLanguageReligion, 
    RelationCaste, 
    RelationFamily
)
from apps.relations.services import RelationLabelService

class RelationManagementPermissionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing relation permissions."""
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = RelationManagementPermissionSerializer
    queryset = RelationManagementPermission.objects.all()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by user if provided
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset.select_related('user', 'user__admin_profile')
    
    @action(detail=False, methods=['get'])
    def my_permissions(self, request):
        """Get current user's relation permissions."""
        try:
            permission = RelationManagementPermission.objects.get(user=request.user)
            serializer = self.get_serializer(permission)
            return Response(serializer.data)
        except RelationManagementPermission.DoesNotExist:
            # Create default permissions if they don't exist
            permission = RelationManagementPermission.objects.create(user=request.user)
            serializer = self.get_serializer(permission)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

class RelationAdminActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing relation management activity logs."""
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = RelationAdminActivityLogSerializer
    queryset = RelationAdminActivityLog.objects.all()
    
    def get_queryset(self):
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
        
        return queryset.select_related('user', 'user__admin_profile')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of relation activities."""
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

class FixedRelationAdminViewSet(viewsets.ModelViewSet):
    """ViewSet for managing FixedRelations (admin only)."""
    permission_classes = [IsAuthenticated]
    serializer_class = FixedRelationSerializer
    queryset = FixedRelation.objects.all()
    
    def get_permissions(self):
        """Custom permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Search by code or name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(relation_code__icontains=search) |
                Q(default_english__icontains=search) |
                Q(default_tamil__icontains=search)
            )
        
        return queryset.annotate(
            family_count=Count('family_labels'),
            caste_count=Count('caste_labels'),
            lang_rel_count=Count('language_religion_labels')
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new fixed relation with logging."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check permissions
        if not self._has_relation_permission(request.user, 'can_manage_fixed_relations'):
            return Response(
                {'error': 'You do not have permission to create fixed relations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        with transaction.atomic():
            relation = serializer.save()
            
            # Log the activity
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
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """Update a fixed relation with logging."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Check permissions
        if not self._has_relation_permission(request.user, 'can_manage_fixed_relations'):
            return Response(
                {'error': 'You do not have permission to update fixed relations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        with transaction.atomic():
            old_data = {
                'relation_code': instance.relation_code,
                'default_english': instance.default_english,
                'default_tamil': instance.default_tamil,
                'category': instance.category
            }
            
            self.perform_update(serializer)
            
            # Log the activity
            RelationAdminActivityLog.objects.create(
                user=request.user,
                action='relation_update',
                description=f'Updated fixed relation: {instance.relation_code}',
                relation_code=instance.relation_code,
                affected_level='fixed',
                ip_address=self.get_client_ip(request),
                metadata={
                    'old_data': old_data,
                    'new_data': serializer.data
                }
            )
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all relation categories."""
        categories = FixedRelation.RELATION_CATEGORIES
        return Response(dict(categories))
    
    @action(detail=True, methods=['get'])
    def overrides(self, request, pk=None):
        """Get all overrides for a specific relation."""
        relation = self.get_object()
        
        overrides = {
            'language_religion': [],
            'caste': [],
            'family': []
        }
        
        # Get language+religion overrides
        lang_rel_overrides = RelationLanguageReligion.objects.filter(relation=relation)
        for override in lang_rel_overrides:
            overrides['language_religion'].append({
                'id': override.id,
                'language': override.language,
                'religion': override.religion,
                'label': override.label,
                'created_at': override.created_at
            })
        
        # Get caste overrides
        caste_overrides = RelationCaste.objects.filter(relation=relation)
        for override in caste_overrides:
            overrides['caste'].append({
                'id': override.id,
                'language': override.language,
                'religion': override.religion,
                'caste': override.caste,
                'label': override.label,
                'created_at': override.created_at
            })
        
        # Get family overrides
        family_overrides = RelationFamily.objects.filter(relation=relation)
        for override in family_overrides:
            overrides['family'].append({
                'id': override.id,
                'language': override.language,
                'religion': override.religion,
                'caste': override.caste,
                'family': override.family,
                'label': override.label,
                'created_at': override.created_at
            })
        
        return Response(overrides)
    
    def _has_relation_permission(self, user, permission_name):
        """Check if user has specific relation permission."""
        if IsAdminUser().has_permission(self.request, self):
            return True
        
        try:
            relation_perm = RelationManagementPermission.objects.get(user=user)
            return getattr(relation_perm, permission_name, False)
        except RelationManagementPermission.DoesNotExist:
            return False
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class RelationOverrideViewSet(viewsets.ViewSet):
    """ViewSet for managing relation overrides."""
    permission_classes = [IsAuthenticated]
    
    def _check_permission(self, user, level):
        """Check if user has permission for specific override level."""
        try:
            relation_perm = RelationManagementPermission.objects.get(user=user)
            
            permission_map = {
                'language_religion': 'can_manage_language_religion',
                'caste': 'can_manage_caste_overrides',
                'family': 'can_manage_family_overrides'
            }
            
            if level in permission_map:
                return getattr(relation_perm, permission_map[level], False)
            
            return False
        except RelationManagementPermission.DoesNotExist:
            return False
    
    @action(detail=False, methods=['post'])
    def create_override(self, request):
        """Create a relation override at specified level."""
        level = request.data.get('level')
        
        if not level or level not in ['language_religion', 'caste', 'family']:
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
            'language_religion': LanguageReligionOverrideSerializer,
            'caste': CasteOverrideSerializer,
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
                if level == 'language_religion':
                    override, created = RelationLanguageReligion.objects.update_or_create(
                        relation=relation,
                        language=data['language'],
                        religion=data['religion'],
                        defaults={'label': data['label']}
                    )
                elif level == 'caste':
                    override, created = RelationCaste.objects.update_or_create(
                        relation=relation,
                        language=data['language'],
                        religion=data['religion'],
                        caste=data['caste'],
                        defaults={'label': data['label']}
                    )
                else:  # family
                    override, created = RelationFamily.objects.update_or_create(
                        relation=relation,
                        language=data['language'],
                        religion=data['religion'],
                        caste=data['caste'],
                        family=data['family'],
                        defaults={'label': data['label']}
                    )
                
                # Log the activity
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
                        'religion': data['religion'],
                        'label': data['label'],
                        'is_new': created
                    }
                )
                
                return Response({
                    'success': True,
                    'message': f'Override {"created" if created else "updated"} successfully',
                    'override_id': override.id,
                    'level': level
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple overrides in bulk."""
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
                        relation = FixedRelation.objects.get(
                            relation_code=override_data['relation_code']
                        )
                        
                        # Create override based on level
                        if level == 'language_religion':
                            obj, created = RelationLanguageReligion.objects.update_or_create(
                                relation=relation,
                                language=override_data['language'],
                                religion=override_data['religion'],
                                defaults={'label': override_data['label']}
                            )
                        elif level == 'caste':
                            obj, created = RelationCaste.objects.update_or_create(
                                relation=relation,
                                language=override_data['language'],
                                religion=override_data['religion'],
                                caste=override_data['caste'],
                                defaults={'label': override_data['label']}
                            )
                        else:  # family
                            obj, created = RelationFamily.objects.update_or_create(
                                relation=relation,
                                language=override_data['language'],
                                religion=override_data['religion'],
                                caste=override_data['caste'],
                                family=override_data['family'],
                                defaults={'label': override_data['label']}
                            )
                        
                        results['success'].append({
                            'index': i,
                            'relation_code': override_data['relation_code'],
                            'created': created
                        })
                        
                    except Exception as e:
                        results['failed'].append({
                            'index': i,
                            'relation_code': override_data.get('relation_code', 'unknown'),
                            'error': str(e)
                        })
                
                # Log bulk activity
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
            
            return Response({
                'success': True,
                'results': results,
                'summary': {
                    'total': len(data['overrides']),
                    'success': len(results['success']),
                    'failed': len(results['failed'])
                }
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['delete'])
    def delete_override(self, request):
        """Delete a relation override."""
        level = request.query_params.get('level')
        override_id = request.query_params.get('id')
        
        if not level or level not in ['language_religion', 'caste', 'family']:
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
        
        try:
            # Get the model based on level
            model_map = {
                'language_religion': RelationLanguageReligion,
                'caste': RelationCaste,
                'family': RelationFamily
            }
            
            model = model_map[level]
            override = model.objects.get(id=override_id)
            relation_code = override.relation.relation_code
            
            # Delete the override
            override.delete()
            
            # Log the activity
            RelationAdminActivityLog.objects.create(
                user=request.user,
                action='override_delete',
                description=f'Deleted {level} override for {relation_code}',
                relation_code=relation_code,
                affected_level=level,
                ip_address=self.get_client_ip(request)
            )
            
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
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search for overrides."""
        level = request.query_params.get('level', 'all')
        language = request.query_params.get('language')
        religion = request.query_params.get('religion')
        caste = request.query_params.get('caste')
        family = request.query_params.get('family')
        relation_code = request.query_params.get('relation_code')
        
        results = []
        
        # Search language+religion overrides
        if level in ['all', 'language_religion']:
            queryset = RelationLanguageReligion.objects.all()
            
            if language:
                queryset = queryset.filter(language=language)
            if religion:
                queryset = queryset.filter(religion=religion)
            if relation_code:
                queryset = queryset.filter(relation__relation_code=relation_code)
            
            for item in queryset:
                results.append({
                    'id': item.id,
                    'level': 'language_religion',
                    'relation_code': item.relation.relation_code,
                    'language': item.language,
                    'religion': item.religion,
                    'label': item.label,
                    'created_at': item.created_at,
                    'default_english': item.relation.default_english,
                    'default_tamil': item.relation.default_tamil
                })
        
        # Search caste overrides
        if level in ['all', 'caste']:
            queryset = RelationCaste.objects.all()
            
            if language:
                queryset = queryset.filter(language=language)
            if religion:
                queryset = queryset.filter(religion=religion)
            if caste:
                queryset = queryset.filter(caste=caste)
            if relation_code:
                queryset = queryset.filter(relation__relation_code=relation_code)
            
            for item in queryset:
                results.append({
                    'id': item.id,
                    'level': 'caste',
                    'relation_code': item.relation.relation_code,
                    'language': item.language,
                    'religion': item.religion,
                    'caste': item.caste,
                    'label': item.label,
                    'created_at': item.created_at,
                    'default_english': item.relation.default_english,
                    'default_tamil': item.relation.default_tamil
                })
        
        # Search family overrides
        if level in ['all', 'family']:
            queryset = RelationFamily.objects.all()
            
            if language:
                queryset = queryset.filter(language=language)
            if religion:
                queryset = queryset.filter(religion=religion)
            if caste:
                queryset = queryset.filter(caste=caste)
            if family:
                queryset = queryset.filter(family=family)
            if relation_code:
                queryset = queryset.filter(relation__relation_code=relation_code)
            
            for item in queryset:
                results.append({
                    'id': item.id,
                    'level': 'family',
                    'relation_code': item.relation.relation_code,
                    'language': item.language,
                    'religion': item.religion,
                    'caste': item.caste,
                    'family': item.family,
                    'label': item.label,
                    'created_at': item.created_at,
                    'default_english': item.relation.default_english,
                    'default_tamil': item.relation.default_tamil
                })
        
        # Sort by creation date
        results.sort(key=lambda x: x['created_at'], reverse=True)
        
        return Response({
            'count': len(results),
            'results': results
        })
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class RelationLabelTestView(generics.GenericAPIView):
    """View for testing relation label resolution."""
    permission_classes = [IsAuthenticated]
    serializer_class = RelationLabelTestSerializer
    
    def post(self, request):
        """Test relation label resolution with given context."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            
            # Get label using RelationLabelService
            label_info = RelationLabelService.get_relation_label(
                relation_code=data['relation_code'],
                language=data['language'],
                religion=data['religion'],
                caste=data['caste'],
                family_name=data.get('family', '')
            )
            
            # Get all possible labels at different levels
            relation = FixedRelation.objects.get(relation_code=data['relation_code'])
            
            # Check family override
            family_override = None
            if data.get('family'):
                family_override = RelationFamily.objects.filter(
                    relation=relation,
                    language=data['language'],
                    religion=data['religion'],
                    caste=data['caste'],
                    family=data['family']
                ).first()
            
            # Check caste override
            caste_override = RelationCaste.objects.filter(
                relation=relation,
                language=data['language'],
                religion=data['religion'],
                caste=data['caste']
            ).first()
            
            # Check language+religion override
            lang_rel_override = RelationLanguageReligion.objects.filter(
                relation=relation,
                language=data['language'],
                religion=data['religion']
            ).first()
            
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
                    'caste': {
                        'exists': caste_override is not None,
                        'label': caste_override.label if caste_override else None
                    },
                    'language_religion': {
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
                    {'level': 'caste', 'used': caste_override is not None and family_override is None},
                    {'level': 'language_religion', 'used': lang_rel_override is not None and caste_override is None and family_override is None},
                    {'level': 'default', 'used': all([
                        family_override is None,
                        caste_override is None,
                        lang_rel_override is None
                    ])}
                ]
            }
            
            return Response(response_data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RelationAnalyticsView(generics.GenericAPIView):
    """View for relation analytics and insights."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get relation analytics."""
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
            RelationLanguageReligion.objects.count() +
            RelationCaste.objects.count() +
            RelationFamily.objects.count()
        )
        
        overrides_by_level = {
            'language_religion': RelationLanguageReligion.objects.count(),
            'caste': RelationCaste.objects.count(),
            'family': RelationFamily.objects.count()
        }
        
        # Most overridden relations
        most_overridden = []
        relations = FixedRelation.objects.annotate(
            total_overrides=Count('family_labels') + Count('caste_labels') + Count('language_religion_labels')
        ).order_by('-total_overrides')[:10]
        
        for relation in relations:
            most_overridden.append({
                'relation_code': relation.relation_code,
                'default_english': relation.default_english,
                'total_overrides': relation.total_overrides,
                'by_level': {
                    'family': relation.family_labels.count(),
                    'caste': relation.caste_labels.count(),
                    'language_religion': relation.language_religion_labels.count()
                }
            })
        
        # Recent activity
        recent_activity = RelationAdminActivityLog.objects.order_by('-created_at')[:10]
        activity_serializer = RelationAdminActivityLogSerializer(recent_activity, many=True)
        
        # Categories breakdown
        categories_breakdown = {}
        for code, name in FixedRelation.RELATION_CATEGORIES:
            count = FixedRelation.objects.filter(category=code).count()
            categories_breakdown[name] = count
        
        analytics_data = {
            'total_relations': total_relations,
            'total_overrides': total_overrides,
            'overrides_by_level': overrides_by_level,
            'most_overridden_relations': most_overridden,
            'recent_activity': activity_serializer.data,
            'categories_breakdown': categories_breakdown,
            'coverage_rate': round((total_overrides / (total_relations * 3)) * 100, 2) if total_relations > 0 else 0
        }
        
        serializer = RelationAnalyticsSerializer(analytics_data)
        return Response(serializer.data)
    
# Add to your existing views.py file
from django.db.models.functions import Lower
from rest_framework.decorators import action

class RelationAutoSuggestViewSet(viewsets.ViewSet):
    """Auto-suggestion endpoints for relation fields."""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def caste(self, request):
        """Auto-suggest caste values (starts with query)."""
        query = request.query_params.get('q', '').strip().lower()
        limit = int(request.query_params.get('limit', 10))
        
        if len(query) < 2:
            return Response({'suggestions': []})
        
        # Get distinct caste values that START with query
        suggestions = RelationCaste.objects.filter(
            caste__istartswith=query
        ).values('caste').annotate(
            count=Count('id'),
            religions=Count('religion', distinct=True)
        ).order_by('-count', 'caste')[:limit]
        
        # If no results with "starts with", fall back to "contains"
        if not suggestions and len(query) >= 2:
            suggestions = RelationCaste.objects.filter(
                caste__icontains=query
            ).values('caste').annotate(
                count=Count('id'),
                religions=Count('religion', distinct=True)
            ).order_by('-count', 'caste')[:limit]
        
        results = [
            {
                'value': item['caste'],
                'label': f"{item['caste']} ({item['count']} uses)",
                'count': item['count'],
                'religions': item['religions']
            }
            for item in suggestions
        ]
        
        return Response({
            'query': query,
            'suggestions': results
        })
    
    @action(detail=False, methods=['get'])
    def family(self, request):
        """Auto-suggest family values (starts with query)."""
        query = request.query_params.get('q', '').strip().lower()
        limit = int(request.query_params.get('limit', 10))
        
        if len(query) < 2:
            return Response({'suggestions': []})
        
        # Get distinct family values that START with query
        suggestions = RelationFamily.objects.filter(
            family__istartswith=query
        ).values('family', 'caste', 'religion').annotate(
            count=Count('id')
        ).order_by('-count', 'family')[:limit]
        
        # Fallback to contains if no results
        if not suggestions and len(query) >= 2:
            suggestions = RelationFamily.objects.filter(
                family__icontains=query
            ).values('family', 'caste', 'religion').annotate(
                count=Count('id')
            ).order_by('-count', 'family')[:limit]
        
        results = [
            {
                'value': item['family'],
                'label': f"{item['family']} ({item['caste']}, {item['count']} uses)",
                'caste': item['caste'],
                'religion': item['religion'],
                'count': item['count']
            }
            for item in suggestions
        ]
        
        return Response({
            'query': query,
            'suggestions': results
        })
    
    @action(detail=False, methods=['get'])
    def relation(self, request):
        """Auto-suggest relation codes (starts with query)."""
        query = request.query_params.get('q', '').strip().lower()
        limit = int(request.query_params.get('limit', 10))
        
        if len(query) < 1:
            return Response({'suggestions': []})
        
        # Search in relation codes (starts with)
        suggestions = FixedRelation.objects.filter(
            Q(relation_code__istartswith=query) |
            Q(default_english__istartswith=query) |
            Q(default_tamil__istartswith=query)
        ).order_by('relation_code')[:limit]
        
        # Fallback to contains
        if not suggestions and len(query) >= 2:
            suggestions = FixedRelation.objects.filter(
                Q(relation_code__icontains=query) |
                Q(default_english__icontains=query) |
                Q(default_tamil__icontains=query)
            ).order_by('relation_code')[:limit]
        
        results = [
            {
                'value': rel.relation_code,
                'label': f"{rel.relation_code} - {rel.default_english}",
                'english': rel.default_english,
                'tamil': rel.default_tamil,
                'category': rel.get_category_display(),
                'overrides': (
                    rel.family_labels.count() +
                    rel.caste_labels.count() +
                    rel.language_religion_labels.count()
                )
            }
            for rel in suggestions
        ]
        
        return Response({
            'query': query,
            'suggestions': results
        })
    
    @action(detail=False, methods=['get'])
    def language(self, request):
        """Auto-suggest language values."""
        query = request.query_params.get('q', '').strip().lower()
        limit = int(request.query_params.get('limit', 10))
        
        if len(query) < 2:
            # Return all languages if query is short
            languages = RelationLanguageReligion.objects.values_list(
                'language', flat=True
            ).distinct().order_by('language')[:limit]
            
            results = [{'value': lang, 'label': lang} for lang in languages]
        else:
            # Filter by query (starts with)
            languages = RelationLanguageReligion.objects.filter(
                language__istartswith=query
            ).values_list('language', flat=True).distinct().order_by('language')[:limit]
            
            results = [{'value': lang, 'label': lang} for lang in languages]
        
        return Response({
            'query': query,
            'suggestions': results
        })
    
    @action(detail=False, methods=['get'])
    def religion(self, request):
        """Auto-suggest religion values."""
        query = request.query_params.get('q', '').strip().lower()
        limit = int(request.query_params.get('limit', 10))
        
        # Get from multiple sources
        religion_set = set()
        
        # From language+religion overrides
        religions_lr = RelationLanguageReligion.objects.filter(
            religion__istartswith=query
        ).values_list('religion', flat=True).distinct()
        religion_set.update(religions_lr)
        
        # From caste overrides
        religions_caste = RelationCaste.objects.filter(
            religion__istartswith=query
        ).values_list('religion', flat=True).distinct()
        religion_set.update(religions_caste)
        
        # If no results with "starts with", try "contains"
        if not religion_set and len(query) >= 2:
            religions_lr = RelationLanguageReligion.objects.filter(
                religion__icontains=query
            ).values_list('religion', flat=True).distinct()
            religion_set.update(religions_lr)
            
            religions_caste = RelationCaste.objects.filter(
                religion__icontains=query
            ).values_list('religion', flat=True).distinct()
            religion_set.update(religions_caste)
        
        # Sort alphabetically
        sorted_religions = sorted(list(religion_set))[:limit]
        
        results = [{'value': rel, 'label': rel} for rel in sorted_religions]
        
        return Response({
            'query': query,
            'suggestions': results
        })
    
    @action(detail=False, methods=['get'])
    def all_fields(self, request):
        """Get all distinct values for dropdowns (no query needed)."""
        # Caste values
        castes = RelationCaste.objects.values_list(
            'caste', flat=True
        ).distinct().order_by('caste')
        
        # Family values
        families = RelationFamily.objects.values_list(
            'family', flat=True
        ).distinct().order_by('family')
        
        # Languages
        languages = RelationLanguageReligion.objects.values_list(
            'language', flat=True
        ).distinct().order_by('language')
        
        # Religions (combined)
        religions_lr = RelationLanguageReligion.objects.values_list(
            'religion', flat=True
        ).distinct()
        religions_caste = RelationCaste.objects.values_list(
            'religion', flat=True
        ).distinct()
        all_religions = sorted(set(list(religions_lr) + list(religions_caste)))
        
        # Relation categories
        categories = dict(FixedRelation.RELATION_CATEGORIES)
        
        return Response({
            'castes': list(castes),
            'families': list(families),
            'languages': list(languages),
            'religions': all_religions,
            'categories': categories
        })
        
        
        
class AdminActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing admin/staff activity logs."""
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminActivityLogSerializer
    queryset = AdminActivityLog.objects.all().order_by('-created_at')
    
    def get_queryset(self):
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
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of admin/staff activities."""
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
            'recent_activities': AdminActivityLogSerializer(
                AdminActivityLog.objects.order_by('-created_at')[:10], 
                many=True,
                context={'request': request}
            ).data
        }
        
        # Count by action type
        actions = AdminActivityLog.objects.values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        for action_data in actions:
            summary['by_action'][action_data['action']] = action_data['count']
        
        # Top users by activity
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
        
        return Response(summary)
    
    

# staff edited by himself

class StaffSelfProfileView(APIView):
    """Allow staff to edit their own complete profile including mobile and email"""
    permission_classes = [IsAuthenticated, IsStaffUser]
    
    def get(self, request):
        """Get staff's own profile"""
        user = request.user
        admin_profile = AdminProfile.objects.get(user=user)
        staff_perm = StaffPermission.objects.get(user=user)
        
        return Response({
            'id': user.id,
            'mobile_number': user.mobile_number,
            'full_name': admin_profile.full_name,
            'email': admin_profile.email,
            'phone': admin_profile.phone,
            'department': admin_profile.department,
            'designation': admin_profile.designation,
            'admin_id': admin_profile.admin_id,
            'user_type': staff_perm.user_type,
            'is_active': staff_perm.is_active,
            'permissions': {
                'can_view_dashboard': staff_perm.can_view_dashboard,
                'can_manage_dashboard': staff_perm.can_manage_dashboard,
                'can_view_users': staff_perm.can_view_users,
                'can_edit_users': staff_perm.can_edit_users,
                'can_export_data': staff_perm.can_export_data,
            }
        })
    
    def patch(self, request):
        """Update own profile - ALL fields including mobile and email"""
        user = request.user
        admin_profile = AdminProfile.objects.get(user=user)
        
        serializer = StaffSelfUpdateSerializer(
            data=request.data,
            context={'request': request, 'user': user},
            partial=True
        )
        
        if serializer.is_valid():
            updated_fields = []
            
            # 1. Update User model (mobile number)
            if 'mobile_number' in serializer.validated_data:
                new_mobile = serializer.validated_data['mobile_number']
                if new_mobile != user.mobile_number:
                    user.mobile_number = new_mobile
                    updated_fields.append('mobile_number')
            
            # 2. Update AdminProfile
            profile_fields = ['full_name', 'email', 'phone', 'department', 'designation']
            for field in profile_fields:
                if field in serializer.validated_data:
                    setattr(admin_profile, field, serializer.validated_data[field])
                    updated_fields.append(field)
            
            # Save changes
            if 'mobile_number' in serializer.validated_data:
                user.save()
            admin_profile.save()
            
            # Log activity
            AdminActivityLog.objects.create(
                user=user,
                action='self_profile_update',
                description=f'Staff updated own profile: {", ".join(updated_fields)}',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'updated_fields': updated_fields
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


class StaffSelfChangePasswordView(APIView):
    """Allow staff to change their own password"""
    permission_classes = [IsAuthenticated, IsStaffUser]
    
    def post(self, request):
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
            
            user.set_password(new_password)
            user.save()
            
            AdminActivityLog.objects.create(
                user=user,
                action='self_password_change',
                description=f'Staff changed own password',
                ip_address=self.get_client_ip(request)
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')