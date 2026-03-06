from rest_framework import serializers
from django.contrib.auth import get_user_model
import re
from .models import StaffPermission, AdminActivityLog, AdminProfile
from django.contrib.auth import authenticate
from rest_framework.exceptions import ValidationError
import logging

from apps.relations.models import (
    FixedRelation, 
    RelationLanguageReligion, 
    RelationCaste, 
    RelationFamily, 
    RelationProfileOverride  # ← ADD THIS LINE
)
from apps.relations.services import RelationLabelService

logger = logging.getLogger(__name__)

User = get_user_model()


# admin_app/serializers.py - Add this at the top with other serializers

class DashboardFilterSerializer(serializers.Serializer):
    """Serializer for dashboard date filters"""
    period = serializers.ChoiceField(
        choices=['today', 'weekly', 'monthly', 'yearly', 'custom'],
        required=False,
        default='all'
    )
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    
    def validate(self, attrs):
        try:
            period = attrs.get('period', 'all')
            start_date = attrs.get('start_date')
            end_date = attrs.get('end_date')
            
            if period == 'custom':
                if not start_date or not end_date:
                    raise serializers.ValidationError(
                        "Both start_date and end_date are required for custom period"
                    )
                if start_date > end_date:
                    raise serializers.ValidationError(
                        "start_date must be before end_date"
                    )
            
            return attrs
        except Exception as e:
            logger.error(f"Error in DashboardFilterSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Validation error: {str(e)}")

class AdminLoginSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=True, max_length=200)
    mobile_number = serializers.CharField(required=True, max_length=15)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        try:
            full_name = attrs.get('full_name').strip()
            mobile_number = attrs.get('mobile_number').strip()
            email = attrs.get('email').strip().lower()
            password = attrs.get('password')
            
            if not re.match(r'^\+?1?\d{10,15}$', mobile_number):
                raise serializers.ValidationError({"mobile_number": "Enter valid mobile number (10-15 digits)"})
            
            try:
                user = User.objects.get(mobile_number=mobile_number)
            except User.DoesNotExist:
                raise serializers.ValidationError({"mobile_number": "No account found with this mobile number"})
            except Exception as e:
                logger.error(f"Error fetching user: {str(e)}")
                raise serializers.ValidationError({"mobile_number": "Error checking mobile number"})
            
            # Verify email from AdminProfile (not User model)
            try:
                admin_profile = AdminProfile.objects.get(user=user)
                if admin_profile.email.lower() != email:
                    raise serializers.ValidationError({"email": "Email does not match the registered email"})
                
                if admin_profile.full_name.lower() != full_name.lower():
                    raise serializers.ValidationError({"full_name": "Name does not match the registered name"})
            except AdminProfile.DoesNotExist:
                raise serializers.ValidationError({"full_name": "Admin profile not found"})
            except Exception as e:
                logger.error(f"Error fetching admin profile: {str(e)}")
                raise serializers.ValidationError({"full_name": "Error verifying admin details"})
            
            # Authenticate user
            try:
                from django.contrib.auth import authenticate
                auth_user = authenticate(username=mobile_number, password=password)
                
                if auth_user is None:
                    raise serializers.ValidationError({"password": "Invalid password"})
            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                raise serializers.ValidationError({"password": "Authentication failed"})
            
            # Check if user is admin/staff
            try:
                staff_perm = StaffPermission.objects.get(user=auth_user)
                if not staff_perm.is_active:
                    raise serializers.ValidationError({"message": "Account is deactivated"})
            except StaffPermission.DoesNotExist:
                raise serializers.ValidationError({"message": "Only admin/staff can login here"})
            except Exception as e:
                logger.error(f"Error checking staff permissions: {str(e)}")
                raise serializers.ValidationError({"message": "Error verifying account permissions"})
            
            attrs['user'] = auth_user
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in AdminLoginSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Login validation failed: {str(e)}")

class AdminRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=True, max_length=200)
    mobile_number = serializers.CharField(required=True, max_length=15)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, min_length=6)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        try:
            mobile_number = attrs.get('mobile_number').strip()
            email = attrs.get('email').strip().lower()
            password = attrs.get('password')
            confirm_password = attrs.get('confirm_password')
            
            if password != confirm_password:
                raise serializers.ValidationError({"confirm_password": "Passwords don't match"})
            
            if not re.match(r'^\+?1?\d{10,15}$', mobile_number):
                raise serializers.ValidationError({"mobile_number": "Enter valid mobile number (10-15 digits)"})
            
            # Check if mobile already exists in User model
            try:
                if User.objects.filter(mobile_number=mobile_number).exists():
                    raise serializers.ValidationError({"mobile_number": "Mobile number already registered"})
            except Exception as e:
                logger.error(f"Error checking mobile number: {str(e)}")
                raise serializers.ValidationError({"mobile_number": "Error checking mobile number"})
            
            # Check if email already exists in AdminProfile (not User model)
            try:
                if AdminProfile.objects.filter(email=email).exists():
                    raise serializers.ValidationError({"email": "Email already registered"})
            except Exception as e:
                logger.error(f"Error checking email: {str(e)}")
                raise serializers.ValidationError({"email": "Error checking email"})
            
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in AdminRegistrationSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Registration validation failed: {str(e)}")
    
    def create(self, validated_data):
        try:
            full_name = validated_data.get('full_name')
            mobile_number = validated_data.get('mobile_number')
            email = validated_data.get('email')
            password = validated_data.get('password')
            
            # Create user WITHOUT email field (your User model doesn't have it)
            user = User.objects.create_user(
                mobile_number,  # First positional argument
                password=password,
                is_staff=True,
                is_superuser=True
            )
            
            # Create admin profile WITH email
            admin_profile = AdminProfile.objects.create(
                user=user,
                full_name=full_name,
                email=email
            )
            
            # Create admin permissions
            StaffPermission.objects.create(
                user=user,
                user_type='admin',
                is_active=True,
                can_manage_admin=True,
                can_edit_users=True,
                can_delete_users=True
            )
            
            return user
        except Exception as e:
            logger.error(f"Error in AdminRegistrationSerializer create: {str(e)}")
            raise serializers.ValidationError(f"Failed to create admin: {str(e)}")
    
    
    
    # staffmanagement

class StaffCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=True, max_length=200)
    mobile_number = serializers.CharField(required=True, max_length=15)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, min_length=6)
    
    def validate(self, attrs):
        try:
            mobile_number = attrs.get('mobile_number').strip()
            email = attrs.get('email').strip().lower()
            
            if not re.match(r'^\+?1?\d{10,15}$', mobile_number):
                raise serializers.ValidationError({"mobile_number": "Enter valid mobile number (10-15 digits)"})
            
            # Check if mobile already exists in User model
            try:
                if User.objects.filter(mobile_number=mobile_number).exists():
                    raise serializers.ValidationError({"mobile_number": "Mobile number already registered"})
            except Exception as e:
                logger.error(f"Error checking mobile number: {str(e)}")
                raise serializers.ValidationError({"mobile_number": "Error checking mobile number"})
            
            # Check if email already exists in AdminProfile
            try:
                if AdminProfile.objects.filter(email=email).exists():
                    raise serializers.ValidationError({"email": "Email already registered"})
            except Exception as e:
                logger.error(f"Error checking email: {str(e)}")
                raise serializers.ValidationError({"email": "Error checking email"})
            
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in StaffCreateSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Staff creation validation failed: {str(e)}")
    
    def create(self, validated_data):
        try:
            full_name = validated_data.get('full_name')
            mobile_number = validated_data.get('mobile_number')
            email = validated_data.get('email')
            password = validated_data.get('password')
            
            # Create user WITHOUT email field
            user = User.objects.create_user(
                mobile_number=mobile_number,  # First positional argument becomes username/USERNAME_FIELD
                password=password,
                is_staff=True
            )
            
            # Check if AdminProfile was already created by signal
            if hasattr(user, 'admin_profile'):
                # Update existing admin profile
                admin_profile = user.admin_profile
                admin_profile.full_name = full_name
                admin_profile.email = email
                admin_profile.save()
            else:
                # Create admin profile WITH email
                AdminProfile.objects.create(
                    user=user,
                    full_name=full_name,
                    email=email
                )
            
            # Check if StaffPermission was already created by signal
            if not hasattr(user, 'staff_permissions'):
                # Create staff permissions
                StaffPermission.objects.create(
                    user=user,
                    user_type='staff',
                    is_active=True
                )
            
            return user
        except Exception as e:
            logger.error(f"Error in StaffCreateSerializer create: {str(e)}")
            raise serializers.ValidationError(f"Failed to create staff: {str(e)}")
    
class StaffDetailSerializer(serializers.ModelSerializer):
    """Serializer for retrieving single staff details"""
    full_name = serializers.CharField(source='admin_profile.full_name')
    email = serializers.EmailField(source='admin_profile.email')
    phone = serializers.CharField(source='admin_profile.phone', allow_null=True)
    department = serializers.CharField(source='admin_profile.department', allow_null=True)
    designation = serializers.CharField(source='admin_profile.designation', allow_null=True)
    admin_id = serializers.CharField(source='admin_profile.admin_id')
    user_type = serializers.CharField(source='staff_permissions.user_type')
    is_active = serializers.BooleanField(source='staff_permissions.is_active')
    created_at = serializers.DateTimeField()
    last_login = serializers.DateTimeField()
    is_mobile_verified = serializers.BooleanField()
    
    # Permissions
    permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'mobile_number', 'full_name', 'email', 'phone',
            'department', 'designation', 'admin_id', 'user_type',
            'is_active', 'is_mobile_verified', 'created_at', 'last_login',
            'permissions'
        ]
    
    def get_permissions(self, obj):
        try:
            if hasattr(obj, 'staff_permissions'):
                perm = obj.staff_permissions
                return {
                    'can_view_dashboard': perm.can_view_dashboard,
                    'can_manage_dashboard': perm.can_manage_dashboard,
                    'can_view_users': perm.can_view_users,
                    'can_edit_users': perm.can_edit_users,
                    'can_export_data': perm.can_export_data,
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting permissions for user {obj.id}: {str(e)}")
            return {}
    
class StaffUpdateSerializer(serializers.Serializer):
    # Profile fields
    full_name = serializers.CharField(required=False, max_length=200)
    mobile_number = serializers.CharField(required=False, max_length=15)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, max_length=15, allow_blank=True, allow_null=True)
    department = serializers.CharField(required=False, max_length=100, allow_blank=True, allow_null=True)
    designation = serializers.CharField(required=False, max_length=100, allow_blank=True, allow_null=True)
   
    
    # Status field
    is_active = serializers.BooleanField(required=False)
    
    # Permission fields
    can_view_dashboard = serializers.BooleanField(required=False)
    can_manage_dashboard = serializers.BooleanField(required=False)
    can_view_users = serializers.BooleanField(required=False)
    can_edit_users = serializers.BooleanField(required=False)
    can_export_data = serializers.BooleanField(required=False)
    
    # ✅ PASSWORD FIELD - Add this
    password = serializers.CharField(required=False, write_only=True, min_length=6)
    
    def validate_mobile_number(self, value):
        try:
            if value:
                if not re.match(r'^\+?1?\d{10,15}$', value):
                    raise serializers.ValidationError("Enter valid mobile number (10-15 digits)")
                
                # Check if mobile exists (excluding current user)
                user = self.context.get('user')
                if User.objects.filter(mobile_number=value).exclude(id=user.id).exists():
                    raise serializers.ValidationError("Mobile number already registered")
            return value
        except Exception as e:
            logger.error(f"Error validating mobile number: {str(e)}")
            raise serializers.ValidationError(f"Mobile number validation error: {str(e)}")
    
    def validate_email(self, value):
        try:
            if value:
                value = value.strip().lower()
                user = self.context.get('user')
                if AdminProfile.objects.filter(email=value).exclude(user=user).exists():
                    raise serializers.ValidationError("Email already registered")
            return value
        except Exception as e:
            logger.error(f"Error validating email: {str(e)}")
            raise serializers.ValidationError(f"Email validation error: {str(e)}")
    
    def update(self, instance, validated_data):
        try:
            # Update User model - mobile number
            if 'mobile_number' in validated_data:
                instance.mobile_number = validated_data['mobile_number']
            
            # ✅ UPDATE PASSWORD - Hash it properly
            if 'password' in validated_data:
                instance.set_password(validated_data['password'])
            
            # Save user if any changes
            if 'mobile_number' in validated_data or 'password' in validated_data:
                instance.save()
            
            # Update AdminProfile
            if hasattr(instance, 'admin_profile'):
                admin_profile = instance.admin_profile
                
                if 'full_name' in validated_data:
                    admin_profile.full_name = validated_data['full_name']
                if 'email' in validated_data:
                    admin_profile.email = validated_data['email']
                if 'phone' in validated_data:
                    admin_profile.phone = validated_data['phone']
                if 'department' in validated_data:
                    admin_profile.department = validated_data['department']
                if 'designation' in validated_data:
                    admin_profile.designation = validated_data['designation']
                
                admin_profile.save()
            
            # Update StaffPermission
            if hasattr(instance, 'staff_permissions'):
                staff_perm = instance.staff_permissions
                
                if 'is_active' in validated_data:
                    staff_perm.is_active = validated_data['is_active']
                if 'can_view_dashboard' in validated_data:
                    staff_perm.can_view_dashboard = validated_data['can_view_dashboard']
                if 'can_manage_dashboard' in validated_data:
                    staff_perm.can_manage_dashboard = validated_data['can_manage_dashboard']
                if 'can_view_users' in validated_data:
                    staff_perm.can_view_users = validated_data['can_view_users']
                if 'can_edit_users' in validated_data:
                    staff_perm.can_edit_users = validated_data['can_edit_users']
                if 'can_export_data' in validated_data:
                    staff_perm.can_export_data = validated_data['can_export_data']
                
                staff_perm.save()
            
            # ✅ Log password change activity
            if 'password' in validated_data:
                request = self.context.get('request')
                if request and request.user:
                    try:
                        AdminActivityLog.objects.create(
                            user=request.user,  # Admin who changed it
                            action='password_change',
                            description=f'Changed password for staff: {instance.admin_profile.full_name}',
                            ip_address=self.get_client_ip(request)
                        )
                    except Exception as e:
                        logger.error(f"Error logging password change: {str(e)}")
            
            return instance
        except Exception as e:
            logger.error(f"Error updating staff {instance.id}: {str(e)}")
            raise serializers.ValidationError(f"Failed to update staff: {str(e)}")
    
    def get_client_ip(self, request):
        try:
            if request:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
            return None
        except Exception as e:
            logger.error(f"Error getting client IP: {str(e)}")
            return None
    
    def to_representation(self, instance):
        """Control the output format - password never returned"""
        try:
            admin_profile = instance.admin_profile
            staff_perm = instance.staff_permissions
            
            return {
                'id': instance.id,
                'mobile_number': instance.mobile_number,
                'full_name': admin_profile.full_name,
                'email': admin_profile.email,
                'phone': admin_profile.phone,
                'department': admin_profile.department,
                'designation': admin_profile.designation,
                'admin_id': admin_profile.admin_id,
                'user_type': staff_perm.user_type,
                'is_active': staff_perm.is_active,
                'is_mobile_verified': instance.is_mobile_verified,
                'created_at': instance.created_at,
                'last_login': instance.last_login,
                'permissions': {
                    'can_view_dashboard': staff_perm.can_view_dashboard,
                    'can_manage_dashboard': staff_perm.can_manage_dashboard,
                    'can_view_users': staff_perm.can_view_users,
                    'can_edit_users': staff_perm.can_edit_users,
                    'can_export_data': staff_perm.can_export_data,
                }
            }
        except Exception as e:
            logger.error(f"Error in to_representation for user {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'mobile_number': instance.mobile_number,
                'error': 'Error loading staff details'
            }

class AdminProfileSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    
    class Meta:
        model = AdminProfile
        fields = ['full_name', 'mobile_number', 'email', 'phone', 
                  'department', 'designation', 'profile_picture',
                  'admin_id', 'is_active', 'created_at']
        read_only_fields = ['admin_id', 'created_at']

class AdminUpdateProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False, max_length=200)
    mobile_number = serializers.CharField(required=False, max_length=15)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, max_length=15)
    department = serializers.CharField(required=False, max_length=100)
    designation = serializers.CharField(required=False, max_length=100)
    profile_picture = serializers.ImageField(required=False)
    
    def validate(self, attrs):
        try:
            request = self.context.get('request')
            if not request:
                return attrs
            
            user = request.user
            mobile_number = attrs.get('mobile_number')
            email = attrs.get('email')
            
            if mobile_number:
                if not re.match(r'^\+?1?\d{10,15}$', mobile_number):
                    raise serializers.ValidationError({"mobile_number": "Enter valid mobile number (10-15 digits)"})
                
                # Check if mobile exists in User model (excluding current user)
                if User.objects.filter(mobile_number=mobile_number).exclude(id=user.id).exists():
                    raise serializers.ValidationError({"mobile_number": "Mobile number already registered with another account"})
            
            if email:
                email = email.strip().lower()
                # Check if email exists in AdminProfile (excluding current user's profile)
                if AdminProfile.objects.filter(email=email).exclude(user=user).exists():
                    raise serializers.ValidationError({"email": "Email already registered with another account"})
            
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in AdminUpdateProfileSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Validation error: {str(e)}")
    
class AdminPasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        try:
            new_password = attrs.get('new_password')
            confirm_password = attrs.get('confirm_password')
            
            if new_password != confirm_password:
                raise serializers.ValidationError({
                    "confirm_password": "Passwords don't match"
                })
            
            if new_password == attrs.get('old_password'):
                raise serializers.ValidationError({
                    "new_password": "New password must be different from old password"
                })
            
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in AdminPasswordChangeSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Password validation error: {str(e)}")


# class AdminPasswordResetSerializer(serializers.Serializer):
#     mobile_number = serializers.CharField(required=True, max_length=15)
#     email = serializers.EmailField(required=True)
    
#     def validate_mobile_number(self, value):
#         if not re.match(r'^\+?1?\d{10,15}$', value):
#             raise serializers.ValidationError("Enter valid mobile number (10-15 digits)")
#         return value


# class AdminPasswordResetConfirmSerializer(serializers.Serializer):
#     token = serializers.CharField(required=True)
#     new_password = serializers.CharField(required=True, write_only=True, min_length=8)
#     confirm_password = serializers.CharField(required=True, write_only=True)
    
#     def validate(self, attrs):
#         new_password = attrs.get('new_password')
#         confirm_password = attrs.get('confirm_password')
        
#         if new_password != confirm_password:
#             raise serializers.ValidationError({
#                 "confirm_password": "Passwords don't match"
#             })
        
#         return attrs

class UserListSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    # ✅ FIX: Get is_active directly from User model, not from staff_permissions
    is_active = serializers.BooleanField(read_only=True)  # Remove source parameter
    
    class Meta:
        model = User
        fields = ['id', 'mobile_number', 'email', 'is_active', 
                  'is_mobile_verified', 'created_at', 'last_login', 'name']
    
    def get_name(self, obj):
        try:
            if hasattr(obj, 'admin_profile'):
                return obj.admin_profile.full_name
            elif hasattr(obj, 'profile'):
                return getattr(obj.profile, 'firstname', obj.mobile_number)
            return obj.mobile_number
        except Exception as e:
            logger.error(f"Error getting name for user {obj.id}: {str(e)}")
            return obj.mobile_number
    
    def get_email(self, obj):
        try:
            if hasattr(obj, 'admin_profile'):
                return obj.admin_profile.email
            return ""
        except Exception as e:
            logger.error(f"Error getting email for user {obj.id}: {str(e)}")
            return ""
    

    
class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    total_users = serializers.IntegerField()
    admin_count = serializers.IntegerField()
    staff_count = serializers.IntegerField()
    regular_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    today_new_users = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    recent_users = serializers.ListField()


class UserDetailSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    profile_info = serializers.SerializerMethodField()
    user_type = serializers.SerializerMethodField()
    is_admin_staff = serializers.SerializerMethodField()
    profile_completion = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'mobile_number', 'email', 'is_active', 
            'is_mobile_verified', 'created_at', 'last_login', 
            'name', 'profile_info', 'user_type', 'is_admin_staff',
            'profile_completion'
        ]
        read_only_fields = fields
    
    def get_name(self, obj):
        """Get user's name from profile"""
        try:
            if hasattr(obj, 'admin_profile'):
                return obj.admin_profile.full_name
            elif hasattr(obj, 'profile'):
                full_name = ""
                if obj.profile.firstname:
                    full_name += obj.profile.firstname
                if obj.profile.secondname:
                    full_name += " " + obj.profile.secondname
                if obj.profile.thirdname:
                    full_name += " " + obj.profile.thirdname
                return full_name.strip() or obj.mobile_number
            return obj.mobile_number
        except Exception as e:
            logger.error(f"Error getting name for user {obj.id}: {str(e)}")
            return obj.mobile_number
    
    def get_email(self, obj):
        try:
            if hasattr(obj, 'admin_profile'):
                return obj.admin_profile.email
            return ""
        except Exception as e:
            logger.error(f"Error getting email for user {obj.id}: {str(e)}")
            return ""
    
    def get_profile_info(self, obj):
        """Get basic profile information"""
        profile_data = {}
        try:
            if hasattr(obj, 'profile'):
                profile = obj.profile
                profile_data = {
                    'firstname': profile.firstname,
                    'secondname': profile.secondname,
                    'thirdname': profile.thirdname,
                    'gender': profile.gender,
                    'dateofbirth': profile.dateofbirth,
                    'age': profile.age,
                    'religion': profile.religion,
                    'caste': profile.caste,
                    'present_city': profile.present_city,
                    'state': profile.state,
                    'nationality': profile.nationality,
                    'preferred_language': profile.preferred_language,
                }
        except Exception as e:
            logger.error(f"Error getting profile info for user {obj.id}: {str(e)}")
        
        return profile_data
    
    def get_user_type(self, obj):
        """Determine user type"""
        try:
            staff_perm = StaffPermission.objects.get(user=obj)
            return staff_perm.user_type
        except StaffPermission.DoesNotExist:
            return 'regular'
        except Exception as e:
            logger.error(f"Error getting user type for {obj.id}: {str(e)}")
            return 'unknown'
    
    def get_is_admin_staff(self, obj):
        """Check if user is admin/staff"""
        try:
            StaffPermission.objects.get(user=obj)
            return True
        except StaffPermission.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking admin/staff status for {obj.id}: {str(e)}")
            return False
    
    def get_profile_completion(self, obj):
        """Calculate profile completion percentage"""
        try:
            if not hasattr(obj, 'profile'):
                return 0
            
            profile = obj.profile
            required_fields = [
                'firstname', 'gender', 'preferred_language',
                'dateofbirth', 'present_city', 'state', 'nationality',
                'familyname1', 'religion', 'caste'
            ]
            
            total = len(required_fields)
            completed = sum(1 for field in required_fields if getattr(profile, field))
            
            return (completed / total * 100) if total > 0 else 0
        except Exception as e:
            logger.error(f"Error calculating profile completion for {obj.id}: {str(e)}")
            return 0
    

# admin_app/serializers.py (add to your existing file)
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import RelationManagementPermission, RelationAdminActivityLog
from apps.relations.models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily
from apps.relations.services import RelationLabelService

User = get_user_model()

class RelationManagementPermissionSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = RelationManagementPermission
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_user_info(self, obj):
        try:
            return {
                'mobile_number': obj.user.mobile_number,
                'full_name': obj.user.admin_profile.full_name if hasattr(obj.user, 'admin_profile') else '',
                'user_type': obj.user.staff_permissions.user_type if hasattr(obj.user, 'staff_permissions') else 'unknown'
            }
        except Exception as e:
            logger.error(f"Error getting user info for permission {obj.id}: {str(e)}")
            return {}

class RelationAdminActivityLogSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = RelationAdminActivityLog
        fields = '__all__'
    
    def get_user_info(self, obj):
        try:
            if obj.user:
                return {
                    'mobile_number': obj.user.mobile_number,
                    'full_name': obj.user.admin_profile.full_name if hasattr(obj.user, 'admin_profile') else '',
                    'admin_id': obj.user.admin_profile.admin_id if hasattr(obj.user, 'admin_profile') else ''
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user info for activity log {obj.id}: {str(e)}")
            return None

class FixedRelationSerializer(serializers.ModelSerializer):
    """Serializer for FixedRelation model."""
    override_counts = serializers.SerializerMethodField()
    recent_activity = serializers.SerializerMethodField()
    
    class Meta:
        model = FixedRelation
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_override_counts(self, obj):
        try:
            return {
                'family': obj.family_labels.count(),
                'caste': obj.caste_labels.count(),
                'language_religion': obj.language_religion_labels.count()
            }
        except Exception as e:
            logger.error(f"Error getting override counts for relation {obj.relation_code}: {str(e)}")
            return {'family': 0, 'caste': 0, 'language_religion': 0}
    
    def get_recent_activity(self, obj):
        try:
            # Get recent override changes for this relation
            from .models import RelationAdminActivityLog
            recent = RelationAdminActivityLog.objects.filter(
                relation_code=obj.relation_code
            ).order_by('-created_at')[:3]
            
            return RelationAdminActivityLogSerializer(recent, many=True).data
        except Exception as e:
            logger.error(f"Error getting recent activity for relation {obj.relation_code}: {str(e)}")
            return []

class RelationOverrideSerializer(serializers.Serializer):
    """Base serializer for relation overrides."""
    relation_code = serializers.CharField(required=True)
    language = serializers.CharField(required=True, max_length=10)
    label = serializers.CharField(required=True, max_length=200)
    
    def validate_relation_code(self, value):
        try:
            if not FixedRelation.objects.filter(relation_code=value).exists():
                raise serializers.ValidationError(f"Invalid relation code: {value}")
            return value
        except Exception as e:
            logger.error(f"Error validating relation code {value}: {str(e)}")
            raise serializers.ValidationError(f"Error validating relation code: {str(e)}")

class LanguageReligionOverrideSerializer(RelationOverrideSerializer):
    """Serializer for language+religion overrides."""
    religion = serializers.CharField(required=True, max_length=100)
    
    class Meta:
        model = RelationLanguageReligion
        fields = ['relation_code', 'language', 'religion', 'label']

class CasteOverrideSerializer(RelationOverrideSerializer):
    """Serializer for caste overrides."""
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    
    class Meta:
        model = RelationCaste
        fields = ['relation_code', 'language', 'religion', 'caste', 'label']

class FamilyOverrideSerializer(RelationOverrideSerializer):
    """Serializer for family overrides."""
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    family = serializers.CharField(required=True, max_length=200)
    
    class Meta:
        model = RelationFamily
        fields = ['relation_code', 'language', 'religion', 'caste', 'family', 'label']

class BulkOverrideSerializer(serializers.Serializer):
    """Serializer for bulk override operations."""
    overrides = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )
    level = serializers.ChoiceField(
        choices=['language_religion', 'caste', 'family'],
        required=True
    )
    
    def validate_overrides(self, value):
        try:
            if not value:
                raise serializers.ValidationError("Overrides list cannot be empty")
            return value
        except Exception as e:
            logger.error(f"Error validating overrides: {str(e)}")
            raise serializers.ValidationError(f"Error validating overrides: {str(e)}")
        
# apps/admin_app/serializers.py (add these serializers)

class RelationProfileOverrideSerializer(serializers.ModelSerializer):
    """Serializer for the unified profile override model."""
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    specificity_score = serializers.IntegerField(source='get_specificity_score', read_only=True)
    
    class Meta:
        model = RelationProfileOverride
        fields = [
            'id', 'relation_code', 'language', 'religion', 'caste', 'family',
            'native', 'present_city', 'taluk', 'district', 'state', 'nationality',
            'label', 'specificity_score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    


class ProfileOverrideCreateSerializer(serializers.Serializer):
    """Serializer for creating/updating profile overrides."""
    relation_code = serializers.CharField(required=True)
    language = serializers.ChoiceField(choices=[('en', 'English'), ('ta', 'Tamil')], default='en')
    
    # All possible override fields (all optional)
    religion = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    caste = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    family = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    native = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    present_city = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    taluk = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    district = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    state = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    
    label = serializers.CharField(required=True, max_length=200)
    
    def validate_relation_code(self, value):
        try:
            if not FixedRelation.objects.filter(relation_code=value).exists():
                raise serializers.ValidationError(f"Invalid relation code: {value}")
            return value
        except Exception as e:
            logger.error(f"Error validating relation code {value}: {str(e)}")
            raise serializers.ValidationError(f"Error validating relation code: {str(e)}")
    
    def validate(self, attrs):
        """Ensure at least one override field is provided."""
        override_fields = [
            'religion', 'caste', 'family', 'native', 'present_city',
            'taluk', 'district', 'state', 'nationality'
        ]
        has_override = any(attrs.get(field) for field in override_fields)
        
        if not has_override:
            raise serializers.ValidationError(
                "At least one override field (religion, caste, family, native, present_city, "
                "taluk, district, state, nationality) must be provided"
            )
        
        return attrs


class ProfileOverrideSearchSerializer(serializers.Serializer):
    """Serializer for searching profile overrides."""
    relation_code = serializers.CharField(required=False)
    language = serializers.CharField(required=False)
    religion = serializers.CharField(required=False)
    caste = serializers.CharField(required=False)
    family = serializers.CharField(required=False)
    native = serializers.CharField(required=False)
    present_city = serializers.CharField(required=False)
    taluk = serializers.CharField(required=False)
    district = serializers.CharField(required=False)
    state = serializers.CharField(required=False)
    nationality = serializers.CharField(required=False)
   
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)


class OverrideAnalyticsSerializer(serializers.Serializer):
    """Serializer for override analytics showing all levels."""
    total_overrides = serializers.IntegerField()
    by_level = serializers.DictField()
    by_relation = serializers.ListField()
    most_specific_overrides = serializers.ListField()
    location_coverage = serializers.DictField()

class RelationLabelTestSerializer(serializers.Serializer):
    """Serializer for testing relation label resolution."""
    relation_code = serializers.CharField(required=True)
    language = serializers.CharField(default='en')
    religion = serializers.CharField(required=True)
    caste = serializers.CharField(required=True)
    family = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        try:
            if not FixedRelation.objects.filter(relation_code=attrs['relation_code']).exists():
                raise serializers.ValidationError(
                    {'relation_code': f"Invalid relation code: {attrs['relation_code']}"}
                )
            return attrs
        except Exception as e:
            logger.error(f"Error validating test params: {str(e)}")
            raise serializers.ValidationError(f"Validation error: {str(e)}")

class RelationAnalyticsSerializer(serializers.Serializer):
    """Serializer for relation analytics."""
    total_relations = serializers.IntegerField()
    total_overrides = serializers.IntegerField()
    overrides_by_level = serializers.DictField()
    most_overridden_relations = serializers.ListField()
    recent_activity = serializers.ListField()
    categories_breakdown = serializers.DictField()
    
    
    
# Add this to your serializers.py
class StaffDashboardStatsSerializer(serializers.Serializer):
    """Serializer for staff dashboard statistics"""
    total_users = serializers.IntegerField()
    regular_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    today_new_users = serializers.IntegerField()
    
    
    week_new_users = serializers.IntegerField()
    active_last_month = serializers.IntegerField()
    recent_users = serializers.ListField()
   
    timestamp = serializers.DateTimeField()
    user_type = serializers.CharField()
    
    
    period = serializers.CharField(required=False, allow_blank=True)
    period_description = serializers.CharField(required=False, allow_blank=True)
    all_time_total_users = serializers.IntegerField(required=False, allow_null=True)
    filter_applied = serializers.DictField(required=False, allow_null=True)
    
class AdminActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for admin/staff activity logs."""
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = AdminActivityLog
        fields = ['id', 'user', 'user_info', 'action', 'description', 
                  'ip_address', 'user_agent', 'created_at']
        read_only_fields = fields
    
    def get_user_info(self, obj):
        try:
            if obj.user:
                user_data = {
                    'id': obj.user.id,
                    'mobile_number': obj.user.mobile_number,
                    'user_type': 'unknown'
                }
                
                # Get admin profile info
                if hasattr(obj.user, 'admin_profile'):
                    user_data['full_name'] = obj.user.admin_profile.full_name
                    user_data['admin_id'] = obj.user.admin_profile.admin_id
                    user_data['email'] = obj.user.admin_profile.email
                
                # Get user type
                if hasattr(obj.user, 'staff_permissions'):
                    user_data['user_type'] = obj.user.staff_permissions.user_type
                    user_data['is_active'] = obj.user.staff_permissions.is_active
                
                return user_data
            return None
        except Exception as e:
            logger.error(f"Error getting user info for activity log {obj.id}: {str(e)}")
            return None
    
# staffselfupdate

class StaffSelfUpdateSerializer(serializers.Serializer):
    """Serializer for staff to update their own profile - ALL fields editable"""
    # All fields are optional for PATCH
    full_name = serializers.CharField(required=False, max_length=200)
    mobile_number = serializers.CharField(required=False, max_length=15)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, max_length=15, allow_blank=True, allow_null=True)
    department = serializers.CharField(required=False, max_length=100, allow_blank=True, allow_null=True)
    designation = serializers.CharField(required=False, max_length=100, allow_blank=True, allow_null=True)
    profile_picture = serializers.ImageField(required=False)
    
    def validate_mobile_number(self, value):
        """Validate mobile number format and uniqueness"""
        try:
            if value:
                # Format validation
                if not re.match(r'^\+?1?\d{10,15}$', value):
                    raise serializers.ValidationError("Enter valid mobile number (10-15 digits)")
                
                # Check uniqueness (excluding current user)
                user = self.context.get('user')
                if User.objects.filter(mobile_number=value).exclude(id=user.id).exists():
                    raise serializers.ValidationError("Mobile number already registered with another account")
            
            return value
        except Exception as e:
            logger.error(f"Error validating mobile number: {str(e)}")
            raise serializers.ValidationError(f"Mobile number validation error: {str(e)}")
    
    def validate_email(self, value):
        """Validate email uniqueness"""
        try:
            if value:
                value = value.strip().lower()
                user = self.context.get('user')
                
                # Check if email exists in AdminProfile (excluding current user's profile)
                if AdminProfile.objects.filter(email=value).exclude(user=user).exists():
                    raise serializers.ValidationError("Email already registered with another account")
            
            return value
        except Exception as e:
            logger.error(f"Error validating email: {str(e)}")
            raise serializers.ValidationError(f"Email validation error: {str(e)}")
    
    def validate(self, attrs):
        """Additional validation"""
        try:
            # If mobile number is being changed, ensure it's not already used
            if 'mobile_number' in attrs:
                # Add any additional validation here
                pass
            
            return attrs
        except Exception as e:
            logger.error(f"Error in StaffSelfUpdateSerializer validate: {str(e)}")
            raise serializers.ValidationError(f"Validation error: {str(e)}")
    
# admin_app/serializers.py

class UserStatsSerializer(serializers.Serializer):
    """Serializer for user statistics"""
    total_users = serializers.IntegerField()
    admin_count = serializers.IntegerField(required=False, allow_null=True)
    staff_count = serializers.IntegerField(required=False, allow_null=True)
    regular_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField(required=False, allow_null=True)  # ✅ ADD THIS
    today_new_users = serializers.IntegerField()
    week_new_users = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    breakdown = serializers.DictField(required=False, allow_null=True)  # Optional breakdown
    
    period = serializers.CharField(required=False, allow_blank=True)
    period_description = serializers.CharField(required=False, allow_blank=True)
    all_time_totals = serializers.DictField(required=False, allow_null=True)
    filter_applied = serializers.DictField(required=False, allow_null=True)
    recent_users = serializers.ListField(required=False, allow_null=True)  # ✅ ADD THIS
    recent_users_count = serializers.IntegerField(required=False, allow_null=True)  # ✅ ADD THIS