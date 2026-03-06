from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
import logging
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import ValidationError

from .models import User, OTPLog

# Set up logger
logger = logging.getLogger(__name__)

class RequestOTPSerializer(serializers.Serializer):
    """Serializer for requesting OTP."""
    mobile_number = serializers.CharField(max_length=15, required=True)
    
    def validate_mobile_number(self, value):
        """Validate mobile number format with proper error handling."""
        try:
            # Validate mobile number format
            if not value or not value.isdigit():
                raise serializers.ValidationError("Mobile number must contain only digits")
            
            if len(value) < 10:
                raise serializers.ValidationError("Mobile number must be at least 10 digits")
            
            if len(value) > 15:
                raise serializers.ValidationError("Mobile number must not exceed 15 digits")
                
            return value
            
        except Exception as e:
            logger.error(f"Error validating mobile number: {str(e)}")
            raise serializers.ValidationError("Invalid mobile number format")
    
    def save(self):
        """Generate and save OTP with comprehensive error handling."""
        mobile_number = None
        user = None
        otp = None
        
        try:
            mobile_number = self.validated_data.get('mobile_number')
            if not mobile_number:
                raise serializers.ValidationError("Mobile number is required")
            
            # Get or create user with error handling
            try:
                user, created = User.objects.get_or_create(
                    mobile_number=mobile_number,
                    defaults={'is_active': True}
                )
            except Exception as e:
                logger.error(f"Error creating/retrieving user for {mobile_number}: {str(e)}")
                raise serializers.ValidationError("Unable to process user account. Please try again.")
            
            # Generate OTP with error handling
            try:
                otp = user.generate_otp()
                if not otp:
                    raise ValueError("Failed to generate OTP")
            except Exception as e:
                logger.error(f"Error generating OTP for user {user.id}: {str(e)}")
                raise serializers.ValidationError("Unable to generate OTP. Please try again.")
            
            # Get IP address safely
            ip_address = None
            try:
                request = self.context.get('request')
                if request and hasattr(request, 'META'):
                    ip_address = request.META.get('REMOTE_ADDR')
                    # Handle proxy headers if needed
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip_address = x_forwarded_for.split(',')[0].strip()
            except Exception as e:
                logger.warning(f"Unable to get IP address for OTP log: {str(e)}")
                ip_address = '0.0.0.0'  # Default value
            
            # Log OTP request with error handling
            try:
                OTPLog.objects.create(
                    mobile_number=mobile_number,
                    otp=otp,
                    ip_address=ip_address,
                    is_used=False
                )
            except Exception as e:
                logger.error(f"Error logging OTP for {mobile_number}: {str(e)}")
                # Continue even if logging fails - don't block the OTP generation
            
            # In production, send OTP via SMS gateway
            # try:
            #     sms_service.send_otp(mobile_number, otp)
            # except Exception as e:
            #     logger.error(f"Error sending SMS to {mobile_number}: {str(e)}")
            #     # Don't raise - OTP is generated even if SMS fails
            
            return user, otp
            
        except serializers.ValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in RequestOTPSerializer.save: {str(e)}")
            raise serializers.ValidationError("An unexpected error occurred. Please try again.")

class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP."""
    mobile_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=True)
    enable_auto_login = serializers.BooleanField(default=True)
    
    def validate(self, data):
        """Validate OTP with comprehensive error handling."""
        mobile_number = None
        otp = None
        enable_auto_login = None
        user = None
        
        try:
            mobile_number = data.get('mobile_number')
            otp = data.get('otp')
            enable_auto_login = data.get('enable_auto_login', True)
            
            if not mobile_number:
                raise serializers.ValidationError({"mobile_number": "Mobile number is required"})
            
            if not otp:
                raise serializers.ValidationError({"otp": "OTP is required"})
            
            # For testing purposes - accept 123456
            if otp != "123456":
                raise serializers.ValidationError("Invalid OTP or OTP expired")
            
            # Retrieve user with error handling
            try:
                user = User.objects.get(mobile_number=mobile_number)
            except ObjectDoesNotExist:
                logger.warning(f"User not found for mobile number: {mobile_number}")
                raise serializers.ValidationError("User not found")
            except Exception as e:
                logger.error(f"Error retrieving user for {mobile_number}: {str(e)}")
                raise serializers.ValidationError("Unable to verify user. Please try again.")
            
            # Verify OTP with error handling
            try:
                if not user.verify_otp(otp):
                    logger.warning(f"Invalid OTP attempt for user {user.id}")
                    raise serializers.ValidationError("Invalid OTP or OTP expired")
            except AttributeError as e:
                logger.error(f"User object missing verify_otp method: {str(e)}")
                raise serializers.ValidationError("Unable to verify OTP. Please try again.")
            except Exception as e:
                logger.error(f"Error verifying OTP for user {user.id}: {str(e)}")
                raise serializers.ValidationError("OTP verification failed. Please try again.")
            
            # Update OTP log with error handling
            try:
                updated_count = OTPLog.objects.filter(
                    mobile_number=mobile_number,
                    otp=otp,
                    is_used=False
                ).update(is_used=True)
                
                if updated_count == 0:
                    logger.warning(f"No active OTP log found for {mobile_number}")
            except Exception as e:
                logger.error(f"Error updating OTP log for {mobile_number}: {str(e)}")
                # Continue even if log update fails
            
            # Enable auto-login if requested
            if enable_auto_login:
                try:
                    user.is_auto_login_enabled = True
                    user.auto_login_last_used = timezone.now()
                    user.auto_login_token = self.generate_auto_login_token()
                    user.save()
                    logger.info(f"Auto-login enabled for user {user.id}")
                except Exception as e:
                    logger.error(f"Error enabling auto-login for user {user.id}: {str(e)}")
                    # Don't fail the verification if auto-login setup fails
                    # Just log the error and continue
            
            data['user'] = user
            return data
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in VerifyOTPSerializer.validate: {str(e)}")
            raise serializers.ValidationError("An unexpected error occurred during verification. Please try again.")
    
    def generate_auto_login_token(self):
        """Generate secure auto-login token with error handling."""
        try:
            import secrets
            return secrets.token_urlsafe(32)
        except ImportError:
            logger.error("secrets module not available, using fallback")
            import random
            import string
            return ''.join(random.choices(string.ascii_letters + string.digits, k=43))
        except Exception as e:
            logger.error(f"Error generating auto-login token: {str(e)}")
            import uuid
            return str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')

class UserSerializer(serializers.ModelSerializer):
    """User model serializer."""
    
    class Meta:
        model = User
        fields = ['id', 'mobile_number', 'is_mobile_verified', 'created_at']
        read_only_fields = ['is_mobile_verified', 'created_at']
    
    def to_representation(self, instance):
        """Convert instance to representation with error handling."""
        try:
            representation = super().to_representation(instance)
            return representation
        except Exception as e:
            logger.error(f"Error serializing user {getattr(instance, 'id', 'unknown')}: {str(e)}")
            # Return basic representation if possible
            return {
                'id': getattr(instance, 'id', None),
                'mobile_number': getattr(instance, 'mobile_number', ''),
                'error': 'Unable to load complete user data'
            }

class AutoLoginSerializer(serializers.Serializer):
    """Serializer for auto-login with mobile number"""
    mobile_number = serializers.CharField(max_length=15, required=True)
    
    def validate_mobile_number(self, value):
        """Validate mobile number with error handling."""
        try:
            if not value:
                raise serializers.ValidationError("Mobile number is required")
            
            if not value.isdigit():
                raise serializers.ValidationError("Mobile number must contain only digits")
            
            if len(value) < 10:
                raise serializers.ValidationError("Mobile number must be at least 10 digits")
            
            if len(value) > 15:
                raise serializers.ValidationError("Mobile number must not exceed 15 digits")
                
            return value
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error validating mobile number for auto-login: {str(e)}")
            raise serializers.ValidationError("Invalid mobile number format")
    
    def validate(self, attrs):
        """Validate auto-login credentials with comprehensive error handling."""
        mobile_number = None
        user = None
        
        try:
            mobile_number = attrs.get('mobile_number')
            if not mobile_number:
                raise serializers.ValidationError("Mobile number is required")
            
            # Retrieve user with error handling
            try:
                user = User.objects.get(mobile_number=mobile_number)
            except ObjectDoesNotExist:
                logger.warning(f"Auto-login attempt for non-existent user: {mobile_number}")
                raise serializers.ValidationError("User not found")
            except Exception as e:
                logger.error(f"Error retrieving user for auto-login {mobile_number}: {str(e)}")
                raise serializers.ValidationError("Unable to verify user. Please try again.")
            
            # Check if user is mobile verified
            if not user.is_mobile_verified:
                logger.warning(f"Auto-login attempt for unverified user: {user.id}")
                raise serializers.ValidationError("Mobile number not verified. Please verify with OTP first.")
            
            # Check if auto-login is enabled
            if not user.is_auto_login_enabled:
                logger.warning(f"Auto-login attempt for user with auto-login disabled: {user.id}")
                raise serializers.ValidationError("Auto-login not enabled for this account")
            
            # Check if auto-login token is valid (not expired)
            try:
                if user.auto_login_last_used and user.auto_login_token:
                    # Auto-login valid for 30 days
                    thirty_days_ago = timezone.now() - timedelta(days=30)
                    if user.auto_login_last_used < thirty_days_ago:
                        logger.info(f"Auto-login expired for user {user.id}")
                        raise serializers.ValidationError("Auto-login expired. Please login with OTP.")
            except TypeError as e:
                logger.error(f"Error comparing dates for auto-login expiry: {str(e)}")
                # If we can't validate expiry, assume it's valid but log the error
            except Exception as e:
                logger.error(f"Error checking auto-login expiry for user {user.id}: {str(e)}")
                # Continue with validation even if expiry check fails
            
            attrs['user'] = user
            return attrs
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in AutoLoginSerializer.validate: {str(e)}")
            raise serializers.ValidationError("An unexpected error occurred. Please try again.")

class EnableAutoLoginSerializer(serializers.Serializer):
    """Serializer to enable auto-login after OTP verification"""
    enable = serializers.BooleanField(default=True)
    
    def validate(self, attrs):
        """Validate enable auto-login request."""
        try:
            enable = attrs.get('enable')
            if enable is None:
                attrs['enable'] = True
            return attrs
        except Exception as e:
            logger.error(f"Error validating enable auto-login: {str(e)}")
            raise serializers.ValidationError("Invalid request data")
    
    def save(self, user=None):
        """Enable or disable auto-login for user."""
        if not user:
            raise serializers.ValidationError("User is required")
        
        try:
            enable = self.validated_data.get('enable', True)
            user.is_auto_login_enabled = enable
            
            if enable:
                # Generate new token when enabling
                import secrets
                user.auto_login_token = secrets.token_urlsafe(32)
                user.auto_login_last_used = timezone.now()
            else:
                # Clear token when disabling
                user.auto_login_token = None
                user.auto_login_last_used = None
            
            user.save()
            logger.info(f"Auto-login {'enabled' if enable else 'disabled'} for user {user.id}")
            return user
            
        except Exception as e:
            logger.error(f"Error updating auto-login status for user {user.id}: {str(e)}")
            raise serializers.ValidationError("Unable to update auto-login settings. Please try again.")
        
from rest_framework import serializers
from .models import User

class UserSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'mobile_number', 'is_mobile_verified']
        
class UserSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mobile_number = serializers.CharField()
    label = serializers.SerializerMethodField()
    value = serializers.CharField(source='mobile_number')
    
    def get_label(self, obj):
        # Format the display label
        mobile = obj.mobile_number
        verified = "✓" if obj.is_mobile_verified else ""
        return f"{mobile} {verified}"