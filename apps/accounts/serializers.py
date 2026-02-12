from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta


from .models import User, OTPLog

class RequestOTPSerializer(serializers.Serializer):
    """Serializer for requesting OTP."""
    mobile_number = serializers.CharField(max_length=15, required=True)
    
    def validate_mobile_number(self, value):
        # Validate mobile number format
        if not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Invalid mobile number")
        return value
    
    def save(self):
        mobile_number = self.validated_data['mobile_number']
        
        # Get or create user
        user, created = User.objects.get_or_create(
            mobile_number=mobile_number,
            defaults={'is_active': True}
        )
        
        # Generate OTP
        otp = user.generate_otp()
        
        # Log OTP request
        OTPLog.objects.create(
            mobile_number=mobile_number,
            otp=otp,
            ip_address=self.context.get('request').META.get('REMOTE_ADDR')
        )
        
        # In production, send OTP via SMS gateway
        # sms_service.send_otp(mobile_number, otp)
        
        return user, otp

class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP."""
    mobile_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=True)
    enable_auto_login = serializers.BooleanField(default=True)  # Add this
    
    def validate(self, data):
        mobile_number = data['mobile_number']
        otp = "123456"
        enable_auto_login = data.get('enable_auto_login', True)
        
        try:
            user = User.objects.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")
        
        if not user.verify_otp(otp):
            raise serializers.ValidationError("Invalid OTP or OTP expired")
        
        # Update OTP log
        OTPLog.objects.filter(
            mobile_number=mobile_number,
            otp="123456",
            is_used=False
        ).update(is_used=True)
        
        # Enable auto-login if requested
        if enable_auto_login:
            user.is_auto_login_enabled = True
            user.auto_login_last_used = timezone.now()
            user.auto_login_token = self.generate_auto_login_token()
            user.save()
        
        data['user'] = user
        return data
    
    def generate_auto_login_token(self):
        import secrets
        return secrets.token_urlsafe(32)

class UserSerializer(serializers.ModelSerializer):
    """User model serializer."""
    
    class Meta:
        model = User
        fields = ['id', 'mobile_number', 'is_mobile_verified', 'created_at']
        read_only_fields = ['is_mobile_verified', 'created_at']
        
class AutoLoginSerializer(serializers.Serializer):
    """Serializer for auto-login with mobile number"""
    mobile_number = serializers.CharField(max_length=15, required=True)
    
    def validate_mobile_number(self, value):
        if not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Invalid mobile number")
        return value
    
    def validate(self, attrs):
        mobile_number = attrs['mobile_number']
        
        try:
            user = User.objects.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")
        
        # Check if user is mobile verified
        if not user.is_mobile_verified:
            raise serializers.ValidationError("Mobile number not verified. Please verify with OTP first.")
        
        # Check if auto-login is enabled
        if not user.is_auto_login_enabled:
            raise serializers.ValidationError("Auto-login not enabled for this account")
        
        # Check if auto-login token is valid (not expired)
        if user.auto_login_last_used and user.auto_login_token:
            # Auto-login valid for 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            if user.auto_login_last_used < thirty_days_ago:
                raise serializers.ValidationError("Auto-login expired. Please login with OTP.")
        
        attrs['user'] = user
        return attrs

class EnableAutoLoginSerializer(serializers.Serializer):
    """Serializer to enable auto-login after OTP verification"""
    enable = serializers.BooleanField(default=True)