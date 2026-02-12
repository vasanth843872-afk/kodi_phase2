from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .models import User
from datetime import timedelta
from django.utils import timezone

from .serializers import RequestOTPSerializer, VerifyOTPSerializer, UserSerializer,AutoLoginSerializer, EnableAutoLoginSerializer

@method_decorator(csrf_exempt, name='dispatch')
class RequestOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RequestOTPSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user, otp = serializer.save()

        # AUTO-CREATE DEFAULT FAMILY (only once)
        from apps.families.models import Family
        from apps.genealogy.models import Person

        if not Person.objects.filter(linked_user=user).exists():
            Family.objects.create(
                family_name=f"{user.mobile_number}'s Family",
                created_by=user,
                description="My family tree"
            )

        return Response(
            {
                'message': 'OTP sent successfully',
                'mobile_number': user.mobile_number
            },
            status=status.HTTP_200_OK
        )


@method_decorator(csrf_exempt, name='dispatch')
class VerifyOTPView(APIView):
    """Verify OTP OR auto-login with token"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        otp = request.data.get('otp')
        auto_login_token = request.data.get('auto_login_token')
        
        # CASE 1: AUTO-LOGIN WITH TOKEN (no OTP needed)
        if auto_login_token and not otp:
            try:
                user = User.objects.get(
                    mobile_number=mobile_number,
                    auto_login_token=auto_login_token,
                    is_auto_login_enabled=True,
                    is_mobile_verified=True
                )
                
                # Check if auto-login not expired (30 days)
                thirty_days_ago = timezone.now() - timedelta(days=30)
                if (user.auto_login_last_used and 
                    user.auto_login_last_used > thirty_days_ago):
                    
                    # Update last used time
                    user.auto_login_last_used = timezone.now()
                    user.save()
                    
                    # Generate new JWT tokens
                    refresh = RefreshToken.for_user(user)
                    
                    return Response({
                        'success': True,
                        'message': 'Auto-login successful',
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                        'user': UserSerializer(user).data,
                        'login_type': 'auto_token',
                        'auto_login_token': auto_login_token  # Return same token
                    })
                
            except User.DoesNotExist:
                pass
            
            # Auto-login failed
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Auto-login expired or invalid'
            })
        
        # CASE 2: REGULAR OTP VERIFICATION
        serializer = VerifyOTPSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            enable_auto_login = serializer.validated_data.get('enable_auto_login', True)
            
            # Enable auto-login for future
            if enable_auto_login:
                user.is_auto_login_enabled = True
                user.auto_login_last_used = timezone.now()
                user.auto_login_token = self.generate_auto_login_token()  # Generate token
                user.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'message': 'Login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'auto_login_enabled': enable_auto_login,
                'auto_login_token': user.auto_login_token if enable_auto_login else None,  # NEW
                'login_type': 'otp_verification'
            })
        
        return Response({
            'success': False,
            'errors': serializer.errors,
            'requires_otp': True
        }, status=status.HTTP_400_BAD_REQUEST)
    
    def generate_auto_login_token(self):
        import secrets
        return secrets.token_urlsafe(32)
    
@method_decorator(csrf_exempt, name='dispatch')
class SmartLoginView(APIView):
    """Smart login: tries auto-login first, falls back to OTP if needed"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        otp = request.data.get('otp')
        
        if not mobile_number:
            return Response(
                {'error': 'Mobile number required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Try to get existing user
            user = User.objects.get(mobile_number=mobile_number)
            
            # ✅ USER EXISTS: Check if we can auto-login
            if not otp:
                # No OTP provided, try auto-login
                return self._handle_auto_login(user, request)
            else:
                # OTP provided, verify it
                return self._handle_otp_login(user, otp, request)
                
        except User.DoesNotExist:
            # ❌ USER DOESN'T EXIST: First time user
            if otp:
                # OTP provided for new user - create and verify
                return self._handle_first_time_user_with_otp(mobile_number, otp, request)
            else:
                # No OTP provided for new user - send OTP
                return self._send_otp_to_new_user(mobile_number, request)
    
    def _handle_auto_login(self, user, request):
        """Handle auto-login for existing users"""
        # Check if user is verified
        if not user.is_mobile_verified:
            return Response({
                'requires_otp': True,
                'message': 'Please verify your mobile number with OTP first'
            })
        
        # Check if auto-login enabled and not expired
        if not user.is_auto_login_enabled:
            return Response({
                'requires_otp': True,
                'message': 'Auto-login not enabled. Please use OTP.'
            })
        
        # Check expiry (30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        if (not user.auto_login_last_used or 
            user.auto_login_last_used < thirty_days_ago):
            return Response({
                'requires_otp': True,
                'message': 'Auto-login expired. Please use OTP.'
            })
        
        # Auto-login successful
        user.auto_login_last_used = timezone.now()
        user.save()
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'message': 'Auto-login successful',
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'login_type': 'auto'
        })
    
    def _handle_otp_login(self, user, otp, request):
        """Handle OTP-based login for existing users"""
        if not user.verify_otp(otp):
            return Response({
                'requires_otp': True,
                'message': 'Invalid OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Mark mobile as verified
        user.is_mobile_verified = True
        user.is_auto_login_enabled = True  # Enable auto-login for future
        user.auto_login_last_used = timezone.now()
        user.save()
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Update OTP log
        from .models import OTPLog
        OTPLog.objects.filter(
            mobile_number=user.mobile_number,
            otp=otp,
            is_used=False
        ).update(is_used=True)
        
        return Response({
            'success': True,
            'message': 'Login successful',
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'login_type': 'otp',
            'auto_login_enabled': True
        })
    
    def _handle_first_time_user_with_otp(self, mobile_number, otp, request):
        """Handle first-time user who provides OTP"""
        # For demo, we'll accept any 6-digit OTP as valid
        if len(otp) != 6 or not otp.isdigit():
            return Response({
                'requires_otp': True,
                'message': 'Invalid OTP format'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new user
        user = User.objects.create(
            mobile_number=mobile_number,
            is_mobile_verified=True,
            is_auto_login_enabled=True  # Enable auto-login for future
        )
        
        # Generate and send OTP (in real app, you'd verify it)
        user.generate_otp()
        
        # Enable auto-login
        user.auto_login_last_used = timezone.now()
        user.save()
        
        # AUTO-CREATE DEFAULT FAMILY (only once)
        from apps.families.models import Family
        from apps.genealogy.models import Person
        
        Family.objects.create(
            family_name=f"{user.mobile_number}'s Family",
            created_by=user,
            description="My family tree"
        )
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Log OTP
        from .models import OTPLog
        OTPLog.objects.create(
            mobile_number=mobile_number,
            otp=otp,
            is_used=True,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return Response({
            'success': True,
            'message': 'Account created and logged in successfully',
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'login_type': 'first_time_otp',
            'auto_login_enabled': True
        })
    
    def _send_otp_to_new_user(self, mobile_number, request):
        """Send OTP to new user"""
        # Create unverified user
        user, created = User.objects.get_or_create(
            mobile_number=mobile_number,
            defaults={
                'is_mobile_verified': False,
                'is_auto_login_enabled': False
            }
        )
        
        # Generate OTP
        otp = user.generate_otp()
        
        # Log OTP request
        from .models import OTPLog
        OTPLog.objects.create(
            mobile_number=mobile_number,
            otp=otp,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # In production, send OTP via SMS
        # sms_service.send_otp(mobile_number, otp)
        
        return Response({
            'requires_otp': True,
            'message': 'OTP sent to your mobile number',
            'mobile_number': mobile_number
        })

class UserDetailView(generics.RetrieveAPIView):
    """Get current user details."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user

class RefreshTokenView(APIView):
    """Refresh JWT token."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            refresh = RefreshToken(refresh_token)
            data = {
                'access': str(refresh.access_token),
            }
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

@method_decorator(csrf_exempt, name='dispatch')
class AutoLoginView(APIView):
    """Auto-login with just mobile number (for verified users)"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = AutoLoginSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Update auto-login timestamp
            user.auto_login_last_used = timezone.now()
            user.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'message': 'Auto-login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'login_type': 'auto_login'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': serializer.errors,
            'requires_otp': True  # Frontend knows to ask for OTP
        }, status=status.HTTP_400_BAD_REQUEST)

@method_decorator(csrf_exempt, name='dispatch')
class CheckLoginStatusView(APIView):
    """Check if user can auto-login or needs OTP"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        
        if not mobile_number:
            return Response({
                'requires_otp': True,
                'message': 'Mobile number required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(mobile_number=mobile_number)
            
            if user.is_mobile_verified and user.is_auto_login_enabled:
                # Check if auto-login expired
                thirty_days_ago = timezone.now() - timedelta(days=30)
                
                if (user.auto_login_last_used and 
                    user.auto_login_last_used > thirty_days_ago):
                    return Response({
                        'can_auto_login': True,
                        'user_name': user.get_name(),  # Add get_name() method to User model
                        'mobile_number': user.mobile_number,
                        'message': 'You can auto-login'
                    })
            
            return Response({
                'can_auto_login': False,
                'requires_otp': True,
                'message': 'OTP required for login'
            })
            
        except User.DoesNotExist:
            return Response({
                'can_auto_login': False,
                'requires_otp': True,
                'message': 'User not found'
            })