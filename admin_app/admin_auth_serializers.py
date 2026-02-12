# from rest_framework import serializers
# from django.contrib.auth import get_user_model
# from django.contrib.auth.password_validation import validate_password
# from .models import AdminProfile, StaffPermission
# import re

# User = get_user_model()

# class AdminRegistrationSerializer(serializers.ModelSerializer):
#     """Serializer for admin registration with email and mobile"""
#     password = serializers.CharField(
#         write_only=True, 
#         required=True,
#         min_length=6,
#         style={'input_type': 'password'}
#     )
#     confirm_password = serializers.CharField(
#         write_only=True, 
#         required=True,
#         style={'input_type': 'password'}
#     )
#     email = serializers.EmailField(required=True)
#     full_name = serializers.CharField(required=True)
#     phone = serializers.CharField(required=False, allow_blank=True)
    
#     class Meta:
#         model = User
#         fields = ['mobile_number', 'email', 'full_name', 'phone', 
#                   'password', 'confirm_password']
    
#     def validate(self, attrs):
#         # Check password match
#         if attrs['password'] != attrs['confirm_password']:
#             raise serializers.ValidationError({
#                 "password": "Passwords don't match"
#             })
        
#         # Check mobile number format
#         mobile = attrs.get('mobile_number')
#         if not re.match(r'^\+?1?\d{9,15}$', mobile):
#             raise serializers.ValidationError({
#                 "mobile_number": "Enter a valid mobile number"
#             })
        
#         # Check if mobile already exists
#         if User.objects.filter(mobile_number=mobile).exists():
#             raise serializers.ValidationError({
#                 "mobile_number": "Mobile number already registered"
#             })
        
#         # Check if email already exists
#         email = attrs.get('email')
#         if User.objects.filter(email=email).exists():
#             raise serializers.ValidationError({
#                 "email": "Email already registered"
#             })
        
#         return attrs
    
#     def create(self, validated_data):
#         # Extract data
#         password = validated_data.pop('password')
#         confirm_password = validated_data.pop('confirm_password')
#         full_name = validated_data.pop('full_name')
#         phone = validated_data.pop('phone', '')
#         email = validated_data.pop('email')
        
#         # Create user
#         user = User.objects.create(
#             mobile_number=validated_data['mobile_number'],
#             email=email,
#             is_staff=True,
#             is_superuser=True
#         )
        
#         # Set password
#         user.set_password(password)
#         user.save()
        
#         # Create admin profile
#         AdminProfile.objects.create(
#             user=user,
#             full_name=full_name,
#             email=email,
#             phone=phone
#         )
        
#         # Create admin permissions
#         StaffPermission.objects.create(
#             user=user,
#             user_type='admin',
#             is_active=True,
#             can_login_with_mobile=True,
#             can_login_with_email=True,
#             can_manage_admin=True,
#             can_edit_users=True,
#             can_delete_users=True
#         )
        
#         return user

# class AdminEmailLoginSerializer(serializers.Serializer):
#     """Serializer for admin login with email"""
#     email = serializers.EmailField(required=True)
#     password = serializers.CharField(
#         required=True, 
#         write_only=True,
#         style={'input_type': 'password'}
#     )
    
#     def validate(self, attrs):
#         email = attrs.get('email')
#         password = attrs.get('password')
        
#         # Find user by email
#         try:
#             user = User.objects.get(email=email)
#         except User.DoesNotExist:
#             raise serializers.ValidationError({
#                 "email": "No account found with this email"
#             })
        
#         # Check if user is admin
#         try:
#             staff_perm = StaffPermission.objects.get(user=user)
#             if staff_perm.user_type != 'admin':
#                 raise serializers.ValidationError({
#                     "email": "Only admin can login with email"
#                 })
            
#             if not staff_perm.can_login_with_email:
#                 raise serializers.ValidationError({
#                     "email": "Email login is disabled for this account"
#                 })
#         except StaffPermission.DoesNotExist:
#             raise serializers.ValidationError({
#                 "email": "Only admin can login with email"
#             })
        
#         # Verify password
#         if not user.check_password(password):
#             raise serializers.ValidationError({
#                 "password": "Invalid password"
#             })
        
#         attrs['user'] = user
#         return attrs

# class AdminProfileSerializer(serializers.ModelSerializer):
#     """Serializer for admin profile"""
#     mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
#     email = serializers.EmailField(source='user.email', read_only=True)
#     is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    
#     class Meta:
#         model = AdminProfile
#         fields = ['admin_id', 'full_name', 'mobile_number', 'email', 
#                   'phone', 'department', 'designation', 'profile_picture',
#                   'is_two_factor_enabled', 'two_factor_method', 
#                   'is_active', 'created_at']
#         read_only_fields = ['admin_id', 'created_at']

# class AdminUpdateProfileSerializer(serializers.ModelSerializer):
#     """Serializer for updating admin profile"""
#     class Meta:
#         model = AdminProfile
#         fields = ['full_name', 'phone', 'department', 'designation', 'profile_picture']
    
#     def update(self, instance, validated_data):
#         # Handle profile picture
#         if 'profile_picture' in validated_data:
#             if instance.profile_picture:
#                 instance.profile_picture.delete(save=False)
#             instance.profile_picture = validated_data['profile_picture']
        
#         # Update other fields
#         for field in ['full_name', 'phone', 'department', 'designation']:
#             if field in validated_data:
#                 setattr(instance, field, validated_data[field])
        
#         instance.save()
#         return instance

# class AdminChangeEmailSerializer(serializers.Serializer):
#     """Serializer for changing admin email"""
#     current_password = serializers.CharField(
#         required=True, 
#         write_only=True,
#         style={'input_type': 'password'}
#     )
#     new_email = serializers.EmailField(required=True)
    
#     def validate(self, attrs):
#         user = self.context['request'].user
        
#         # Verify current password
#         if not user.check_password(attrs['current_password']):
#             raise serializers.ValidationError({
#                 "current_password": "Current password is incorrect"
#             })
        
#         # Check if new email already exists
#         new_email = attrs['new_email']
#         if User.objects.filter(email=new_email).exclude(id=user.id).exists():
#             raise serializers.ValidationError({
#                 "new_email": "Email already registered with another account"
#             })
        
#         return attrs

# class AdminForgotPasswordSerializer(serializers.Serializer):
#     """Serializer for forgot password"""
#     email = serializers.EmailField(required=True)
    
#     def validate_email(self, value):
#         # Check if email exists and belongs to an admin
#         try:
#             user = User.objects.get(email=value)
#             staff_perm = StaffPermission.objects.get(user=user)
#             if staff_perm.user_type != 'admin':
#                 raise serializers.ValidationError(
#                     "Only admin accounts can use this feature"
#                 )
#         except User.DoesNotExist:
#             raise serializers.ValidationError("No admin account found with this email")
#         except StaffPermission.DoesNotExist:
#             raise serializers.ValidationError("Invalid admin account")
        
#         return value

# class AdminResetPasswordSerializer(serializers.Serializer):
#     """Serializer for resetting password"""
#     token = serializers.CharField(required=True)
#     new_password = serializers.CharField(
#         required=True, 
#         write_only=True,
#         min_length=6,
#         style={'input_type': 'password'}
#     )
#     confirm_password = serializers.CharField(
#         required=True, 
#         write_only=True,
#         style={'input_type': 'password'}
#     )
    
#     def validate(self, attrs):
#         if attrs['new_password'] != attrs['confirm_password']:
#             raise serializers.ValidationError({
#                 "confirm_password": "Passwords don't match"
#             })
#         return attrs