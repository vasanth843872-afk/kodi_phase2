from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError, DatabaseError, transaction
from django.utils import timezone
from datetime import timedelta
import logging
import traceback
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound

from .models import User
from .serializers import (
    RequestOTPSerializer, VerifyOTPSerializer, UserSerializer,
    AutoLoginSerializer, EnableAutoLoginSerializer
)

# Set up logger
logger = logging.getLogger(__name__)

# Custom exception handler for consistent error responses
def handle_exception(e, context=None):
    """Centralized exception handling for consistent error responses"""
    error_id = str(uuid.uuid4())[:8]  # Generate error ID for tracking
    
    if isinstance(e, (serializers.ValidationError, DjangoValidationError)):
        logger.warning(f"Validation error [{error_id}]: {str(e)}")
        return {
            'success': False,
            'error_type': 'validation_error',
            'errors': e.detail if hasattr(e, 'detail') else str(e),
            'error_id': error_id
        }, status.HTTP_400_BAD_REQUEST
    
    elif isinstance(e, ObjectDoesNotExist):
        logger.warning(f"Resource not found [{error_id}]: {str(e)}")
        return {
            'success': False,
            'error_type': 'not_found',
            'message': 'The requested resource was not found',
            'error_id': error_id
        }, status.HTTP_404_NOT_FOUND
    
    elif isinstance(e, (AuthenticationFailed, PermissionDenied)):
        logger.warning(f"Authentication error [{error_id}]: {str(e)}")
        return {
            'success': False,
            'error_type': 'authentication_error',
            'message': str(e),
            'error_id': error_id
        }, status.HTTP_401_UNAUTHORIZED
    
    elif isinstance(e, DatabaseError):
        logger.error(f"Database error [{error_id}]: {str(e)}\n{traceback.format_exc()}")
        return {
            'success': False,
            'error_type': 'database_error',
            'message': 'A database error occurred. Please try again.',
            'error_id': error_id
        }, status.HTTP_500_INTERNAL_SERVER_ERROR
    
    elif isinstance(e, IntegrityError):
        logger.error(f"Integrity error [{error_id}]: {str(e)}\n{traceback.format_exc()}")
        return {
            'success': False,
            'error_type': 'integrity_error',
            'message': 'Data integrity error. Please check your input.',
            'error_id': error_id
        }, status.HTTP_400_BAD_REQUEST
    
    else:
        logger.error(f"Unexpected error [{error_id}]: {str(e)}\n{traceback.format_exc()}")
        return {
            'success': False,
            'error_type': 'server_error',
            'message': 'An unexpected error occurred. Our team has been notified.',
            'error_id': error_id
        }, status.HTTP_500_INTERNAL_SERVER_ERROR

import uuid

@method_decorator(csrf_exempt, name='dispatch')
class RequestOTPView(APIView):
    """View for requesting OTP with comprehensive error handling"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            # Validate input data
            serializer = RequestOTPSerializer(
                data=request.data,
                context={'request': request}
            )

            if not serializer.is_valid():
                logger.warning(f"OTP request validation failed: {serializer.errors}")
                return Response(
                    {
                        'success': False,
                        'error_type': 'validation_error',
                        'errors': serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate OTP and create/update user
            try:
                with transaction.atomic():
                    user, otp = serializer.save()
                    
                    # AUTO-CREATE DEFAULT FAMILY (only once)
                    try:
                        from apps.families.models import Family
                        from apps.genealogy.models import Person
                        
                        # Check if person exists before creating family
                        person_exists = False
                        try:
                            person_exists = Person.objects.filter(linked_user=user).exists()
                        except Exception as e:
                            logger.error(f"Error checking person existence: {str(e)}")
                        
                        if not person_exists:
                            try:
                                family = Family.objects.create(
                                    family_name=f"{user.mobile_number}'s Family",
                                    created_by=user,
                                    description="My family tree"
                                )
                                logger.info(f"Created default family {family.id} for user {user.id}")
                            except Exception as e:
                                logger.error(f"Error creating default family: {str(e)}")
                                # Don't fail OTP generation if family creation fails
                    except ImportError as e:
                        logger.error(f"Could not import family models: {str(e)}")
                    except Exception as e:
                        logger.error(f"Unexpected error in family creation: {str(e)}")
                    
                    # ------------------------------
                    # CHECK AUTO-LOGIN ELIGIBILITY
                    # ------------------------------
                    can_auto_login = False
                    auto_login_token = None
                    
                    if user.is_mobile_verified and user.is_auto_login_enabled and user.auto_login_token:
                        thirty_days_ago = timezone.now() - timedelta(days=30)
                        if user.auto_login_last_used and user.auto_login_last_used > thirty_days_ago:
                            can_auto_login = True
                            auto_login_token = user.auto_login_token
                        else:
                            logger.info(f"Auto-login expired for user {user.id}")
                    else:
                        logger.debug(f"Auto-login not available for user {user.id}: verified={user.is_mobile_verified}, enabled={user.is_auto_login_enabled}, token_exists={bool(user.auto_login_token)}")
                    
                    return Response(
                        {
                            'success': True,
                            'message': 'OTP sent successfully',
                            'mobile_number': user.mobile_number,
                            'is_new_user': user.created_at > timezone.now() - timedelta(seconds=10),
                            'can_auto_login': can_auto_login,
                            'auto_login_token': auto_login_token   # Only present if can_auto_login is True
                        },
                        status=status.HTTP_200_OK
                    )
                    
            except serializers.ValidationError as e:
                logger.warning(f"OTP generation validation error: {str(e)}")
                return Response(
                    {
                        'success': False,
                        'error_type': 'validation_error',
                        'message': str(e)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            except DatabaseError as e:
                logger.error(f"Database error during OTP generation: {str(e)}")
                return Response(
                    {
                        'success': False,
                        'error_type': 'database_error',
                        'message': 'Unable to process request due to database error'
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)


@method_decorator(csrf_exempt, name='dispatch')
class VerifyOTPView(APIView):
    """Verify OTP OR auto-login with token - with comprehensive error handling"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            mobile_number = request.data.get('mobile_number')
            otp = request.data.get('otp')
            auto_login_token = request.data.get('auto_login_token')
            
            # Validate required fields
            if not mobile_number:
                return Response(
                    {
                        'success': False,
                        'error_type': 'validation_error',
                        'message': 'Mobile number is required'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # CASE 1: AUTO-LOGIN WITH TOKEN (no OTP needed)
            if auto_login_token and not otp:
                return self._handle_auto_login_token(mobile_number, auto_login_token)
            
            # CASE 2: REGULAR OTP VERIFICATION
            elif otp:
                return self._handle_otp_verification(request, mobile_number, otp)
            
            else:
                return Response(
                    {
                        'success': False,
                        'error_type': 'validation_error',
                        'requires_otp': True,
                        'message': 'Either OTP or auto-login token is required'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)
    
    def _handle_auto_login_token(self, mobile_number, auto_login_token):
        """Handle auto-login with token"""
        try:
            # Validate token format
            if not auto_login_token or len(auto_login_token) < 10:
                logger.warning(f"Invalid auto-login token format for {mobile_number}")
                return Response(
                    {
                        'success': False,
                        'requires_otp': True,
                        'message': 'Invalid auto-login token'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find user with matching token
            try:
                user = User.objects.get(
                    mobile_number=mobile_number,
                    auto_login_token=auto_login_token,
                    is_auto_login_enabled=True,
                    is_mobile_verified=True
                )
            except ObjectDoesNotExist:
                logger.warning(f"Auto-login failed: No user found with token for {mobile_number}")
                return Response(
                    {
                        'success': False,
                        'requires_otp': True,
                        'message': 'Auto-login expired or invalid'
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            except DatabaseError as e:
                logger.error(f"Database error during auto-login lookup: {str(e)}")
                return Response(
                    {
                        'success': False,
                        'requires_otp': True,
                        'message': 'Unable to verify auto-login. Please use OTP.'
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Check if auto-login not expired (30 days)
            try:
                thirty_days_ago = timezone.now() - timedelta(days=30)
                if (user.auto_login_last_used and 
                    user.auto_login_last_used > thirty_days_ago):
                    
                    # Update last used time within transaction
                    try:
                        with transaction.atomic():
                            user.auto_login_last_used = timezone.now()
                            user.save()
                    except DatabaseError as e:
                        logger.error(f"Error updating auto-login timestamp: {str(e)}")
                        # Continue even if update fails
                    
                    # Generate new JWT tokens
                    try:
                        refresh = RefreshToken.for_user(user)
                    except Exception as e:
                        logger.error(f"Error generating JWT tokens: {str(e)}")
                        return Response(
                            {
                                'success': False,
                                'requires_otp': True,
                                'message': 'Unable to generate authentication tokens'
                            },
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                    
                    logger.info(f"Auto-login successful for user {user.id}")
                    return Response({
                        'success': True,
                        'message': 'Auto-login successful',
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                        'user': UserSerializer(user).data,
                        'login_type': 'auto_token',
                        'auto_login_token': auto_login_token  # Return same token
                    })
                else:
                    logger.info(f"Auto-login expired for user {user.id}")
                    return Response({
                        'success': False,
                        'requires_otp': True,
                        'message': 'Auto-login expired. Please login with OTP.'
                    })
                    
            except Exception as e:
                logger.error(f"Error checking auto-login expiry: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to verify auto-login status'
                })
                
        except Exception as e:
            logger.error(f"Unexpected error in auto-login: {str(e)}")
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Auto-login failed. Please use OTP.'
            })
    
    def _handle_otp_verification(self, request, mobile_number, otp):
        """Handle OTP verification"""
        try:
            # Validate OTP format
            if not otp or not isinstance(otp, str) or len(otp) != 6:
                return Response({
                    'success': False,
                    'errors': {'otp': ['OTP must be 6 digits']},
                    'requires_otp': True
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify OTP
            serializer = VerifyOTPSerializer(data=request.data)
            
            if serializer.is_valid():
                try:
                    user = serializer.validated_data['user']
                    enable_auto_login = serializer.validated_data.get('enable_auto_login', True)
                    
                    # Enable auto-login for future
                    if enable_auto_login:
                        try:
                            with transaction.atomic():
                                user.is_auto_login_enabled = True
                                user.auto_login_last_used = timezone.now()
                                user.auto_login_token = self.generate_auto_login_token()
                                user.save()
                        except DatabaseError as e:
                            logger.error(f"Error enabling auto-login: {str(e)}")
                            # Continue even if auto-login setup fails
                    
                    # Generate JWT tokens
                    try:
                        refresh = RefreshToken.for_user(user)
                    except Exception as e:
                        logger.error(f"Error generating JWT tokens: {str(e)}")
                        return Response({
                            'success': False,
                            'requires_otp': True,
                            'message': 'Unable to generate authentication tokens'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                    logger.info(f"OTP verification successful for user {user.id}")
                    return Response({
                        'success': True,
                        'message': 'Login successful',
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                        'user': UserSerializer(user).data,
                        'auto_login_enabled': enable_auto_login,
                        'auto_login_token': user.auto_login_token if enable_auto_login else None,
                        'login_type': 'otp_verification'
                    })
                    
                except KeyError as e:
                    logger.error(f"Missing key in validated data: {str(e)}")
                    return Response({
                        'success': False,
                        'errors': {'error': 'Invalid response data'},
                        'requires_otp': True
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Handle validation errors
            logger.warning(f"OTP verification failed: {serializer.errors}")
            return Response({
                'success': False,
                'errors': serializer.errors,
                'requires_otp': True
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Unexpected error in OTP verification: {str(e)}")
            return Response({
                'success': False,
                'errors': {'error': 'Verification failed'},
                'requires_otp': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def generate_auto_login_token(self):
        """Generate secure auto-login token with fallback"""
        try:
            import secrets
            return secrets.token_urlsafe(32)
        except ImportError:
            logger.warning("secrets module not available, using fallback")
            import random
            import string
            return ''.join(random.choices(string.ascii_letters + string.digits, k=43))
        except Exception as e:
            logger.error(f"Error generating token: {str(e)}")
            import uuid
            return str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')


@method_decorator(csrf_exempt, name='dispatch')
class SmartLoginView(APIView):
    """Smart login: tries auto-login first, falls back to OTP if needed"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            mobile_number = request.data.get('mobile_number')
            otp = request.data.get('otp')
            
            if not mobile_number:
                return Response(
                    {
                        'success': False,
                        'error': 'Mobile number required',
                        'requires_otp': True
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate mobile number format
            if not mobile_number.isdigit() or len(mobile_number) < 10:
                return Response(
                    {
                        'success': False,
                        'error': 'Invalid mobile number format',
                        'requires_otp': True
                    },
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
                    
            except ObjectDoesNotExist:
                # ❌ USER DOESN'T EXIST: First time user
                if otp:
                    # OTP provided for new user - create and verify
                    return self._handle_first_time_user_with_otp(mobile_number, otp, request)
                else:
                    # No OTP provided for new user - send OTP
                    return self._send_otp_to_new_user(mobile_number, request)
                    
            except DatabaseError as e:
                logger.error(f"Database error in SmartLoginView: {str(e)}")
                return Response(
                    {
                        'success': False,
                        'error': 'Unable to process login due to database error',
                        'requires_otp': True
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)
    
    def _handle_auto_login(self, user, request):
        """Handle auto-login for existing users"""
        try:
            # Check if user is verified
            if not user.is_mobile_verified:
                logger.info(f"Auto-login attempted for unverified user {user.id}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Please verify your mobile number with OTP first'
                })
            
            # Check if auto-login enabled and not expired
            if not user.is_auto_login_enabled:
                logger.info(f"Auto-login attempted for user {user.id} with auto-login disabled")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Auto-login not enabled. Please use OTP.'
                })
            
            # Check expiry (30 days)
            try:
                thirty_days_ago = timezone.now() - timedelta(days=30)
                if (not user.auto_login_last_used or 
                    user.auto_login_last_used < thirty_days_ago):
                    logger.info(f"Auto-login expired for user {user.id}")
                    return Response({
                        'success': False,
                        'requires_otp': True,
                        'message': 'Auto-login expired. Please use OTP.'
                    })
            except Exception as e:
                logger.error(f"Error checking auto-login expiry: {str(e)}")
                # If we can't check expiry, require OTP
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to verify auto-login status. Please use OTP.'
                })
            
            # Auto-login successful
            try:
                with transaction.atomic():
                    user.auto_login_last_used = timezone.now()
                    user.save()
            except DatabaseError as e:
                logger.error(f"Error updating auto-login timestamp: {str(e)}")
                # Continue even if update fails
            
            # Generate tokens
            try:
                refresh = RefreshToken.for_user(user)
            except Exception as e:
                logger.error(f"Error generating JWT tokens: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to generate authentication tokens'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info(f"Auto-login successful for user {user.id}")
            return Response({
                'success': True,
                'message': 'Auto-login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'login_type': 'auto'
            })
            
        except Exception as e:
            logger.error(f"Unexpected error in auto-login handler: {str(e)}")
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Auto-login failed. Please use OTP.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _handle_otp_login(self, user, otp, request):
        """Handle OTP-based login for existing users"""
        try:
            # Verify OTP
            try:
                if not user.verify_otp(otp):
                    logger.warning(f"Invalid OTP attempt for user {user.id}")
                    return Response({
                        'success': False,
                        'requires_otp': True,
                        'message': 'Invalid OTP'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Error verifying OTP: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to verify OTP. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Update user status
            try:
                with transaction.atomic():
                    user.is_mobile_verified = True
                    user.is_auto_login_enabled = True
                    user.auto_login_last_used = timezone.now()
                    user.save()
            except DatabaseError as e:
                logger.error(f"Error updating user after OTP verification: {str(e)}")
                # Continue even if update fails - user is still verified
            
            # Generate tokens
            try:
                refresh = RefreshToken.for_user(user)
            except Exception as e:
                logger.error(f"Error generating JWT tokens: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to generate authentication tokens'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Update OTP log
            try:
                from .models import OTPLog
                updated = OTPLog.objects.filter(
                    mobile_number=user.mobile_number,
                    otp=otp,
                    is_used=False
                ).update(is_used=True)
                if updated == 0:
                    logger.warning(f"No active OTP log found for {user.mobile_number}")
            except Exception as e:
                logger.error(f"Error updating OTP log: {str(e)}")
                # Don't fail login if log update fails
            
            logger.info(f"OTP login successful for user {user.id}")
            return Response({
                'success': True,
                'message': 'Login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'login_type': 'otp',
                'auto_login_enabled': True
            })
            
        except Exception as e:
            logger.error(f"Unexpected error in OTP login handler: {str(e)}")
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Login failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _handle_first_time_user_with_otp(self, mobile_number, otp, request):
        """Handle first-time user who provides OTP"""
        try:
            # Validate OTP format
            if not otp or len(otp) != 6 or not otp.isdigit():
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Invalid OTP format'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create new user within transaction
            try:
                with transaction.atomic():
                    user = User.objects.create(
                        mobile_number=mobile_number,
                        is_mobile_verified=True,
                        is_auto_login_enabled=True
                    )
                    
                    # Generate and send OTP (in real app, you'd verify it)
                    try:
                        user.generate_otp()
                    except Exception as e:
                        logger.error(f"Error generating OTP for new user: {str(e)}")
                        # Continue even if OTP generation fails
                    
                    # Enable auto-login
                    user.auto_login_last_used = timezone.now()
                    user.save()
                    
            except IntegrityError as e:
                logger.error(f"Integrity error creating user: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to create user account. Please try again.'
                }, status=status.HTTP_400_BAD_REQUEST)
            except DatabaseError as e:
                logger.error(f"Database error creating user: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to create user account due to database error'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # AUTO-CREATE DEFAULT FAMILY (only once)
            try:
                from apps.families.models import Family
                from apps.genealogy.models import Person
                
                Family.objects.create(
                    family_name=f"{user.mobile_number}'s Family",
                    created_by=user,
                    description="My family tree"
                )
                logger.info(f"Created default family for new user {user.id}")
            except ImportError as e:
                logger.error(f"Could not import family models: {str(e)}")
            except Exception as e:
                logger.error(f"Error creating default family: {str(e)}")
                # Don't fail user creation if family creation fails
            
            # Generate tokens
            try:
                refresh = RefreshToken.for_user(user)
            except Exception as e:
                logger.error(f"Error generating JWT tokens: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to generate authentication tokens'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Log OTP
            try:
                from .models import OTPLog
                OTPLog.objects.create(
                    mobile_number=mobile_number,
                    otp=otp,
                    is_used=True,
                    ip_address=request.META.get('REMOTE_ADDR', '0.0.0.0')
                )
            except Exception as e:
                logger.error(f"Error logging OTP: {str(e)}")
                # Continue even if logging fails
            
            logger.info(f"New user created and logged in: {user.id}")
            return Response({
                'success': True,
                'message': 'Account created and logged in successfully',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'login_type': 'first_time_otp',
                'auto_login_enabled': True
            })
            
        except Exception as e:
            logger.error(f"Unexpected error creating new user: {str(e)}")
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Unable to create account. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_otp_to_new_user(self, mobile_number, request):
        """Send OTP to new user"""
        try:
            # Create unverified user within transaction
            try:
                with transaction.atomic():
                    user, created = User.objects.get_or_create(
                        mobile_number=mobile_number,
                        defaults={
                            'is_mobile_verified': False,
                            'is_auto_login_enabled': False
                        }
                    )
            except IntegrityError as e:
                logger.error(f"Integrity error creating user: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to process request. Please try again.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate OTP
            try:
                otp = user.generate_otp()
                if not otp:
                    raise ValueError("Failed to generate OTP")
            except Exception as e:
                logger.error(f"Error generating OTP: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to generate OTP. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Log OTP request
            try:
                from .models import OTPLog
                OTPLog.objects.create(
                    mobile_number=mobile_number,
                    otp=otp,
                    ip_address=request.META.get('REMOTE_ADDR', '0.0.0.0')
                )
            except Exception as e:
                logger.error(f"Error logging OTP: {str(e)}")
                # Continue even if logging fails
            
            # In production, send OTP via SMS
            # try:
            #     sms_service.send_otp(mobile_number, otp)
            # except Exception as e:
            #     logger.error(f"Error sending SMS: {str(e)}")
            
            logger.info(f"OTP sent to new user: {mobile_number}")
            return Response({
                'success': True,
                'requires_otp': True,
                'message': 'OTP sent to your mobile number',
                'mobile_number': mobile_number
            })
            
        except Exception as e:
            logger.error(f"Unexpected error sending OTP to new user: {str(e)}")
            return Response({
                'success': False,
                'requires_otp': True,
                'message': 'Unable to send OTP. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserDetailView(generics.RetrieveAPIView):
    """Get current user details."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Get current user with error handling"""
        try:
            return self.request.user
        except AttributeError:
            logger.error("Request has no user attribute")
            raise NotFound("User not found")
        except Exception as e:
            logger.error(f"Error retrieving user details: {str(e)}")
            raise
    
    def handle_exception(self, exc):
        """Custom exception handling for this view"""
        if isinstance(exc, NotFound):
            return Response(
                {
                    'success': False,
                    'error_type': 'not_found',
                    'message': str(exc)
                },
                status=status.HTTP_404_NOT_FOUND
            )
        elif isinstance(exc, PermissionDenied):
            return Response(
                {
                    'success': False,
                    'error_type': 'permission_denied',
                    'message': 'You do not have permission to access this resource'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        return super().handle_exception(exc)


class RefreshTokenView(APIView):
    """Refresh JWT token."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {
                        'success': False,
                        'error': 'Refresh token is required'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate token format
            if not isinstance(refresh_token, str) or len(refresh_token) < 10:
                return Response(
                    {
                        'success': False,
                        'error': 'Invalid token format'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                refresh = RefreshToken(refresh_token)
                data = {
                    'success': True,
                    'access': str(refresh.access_token),
                }
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as e:
                logger.warning(f"Token refresh failed: {str(e)}")
                return Response(
                    {
                        'success': False,
                        'error': 'Invalid or expired refresh token'
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
                
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)


@method_decorator(csrf_exempt, name='dispatch')
class AutoLoginView(APIView):
    """Auto-login with just mobile number (for verified users)"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            serializer = AutoLoginSerializer(data=request.data)
            
            if serializer.is_valid():
                try:
                    user = serializer.validated_data['user']
                    
                    # Update auto-login timestamp within transaction
                    try:
                        with transaction.atomic():
                            user.auto_login_last_used = timezone.now()
                            user.save()
                    except DatabaseError as e:
                        logger.error(f"Error updating auto-login timestamp: {str(e)}")
                        # Continue even if update fails
                    
                    # Generate JWT tokens
                    try:
                        refresh = RefreshToken.for_user(user)
                    except Exception as e:
                        logger.error(f"Error generating JWT tokens: {str(e)}")
                        return Response({
                            'success': False,
                            'requires_otp': True,
                            'message': 'Unable to generate authentication tokens'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                    logger.info(f"Auto-login successful for user {user.id}")
                    return Response({
                        'success': True,
                        'message': 'Auto-login successful',
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                        'user': UserSerializer(user).data,
                        'login_type': 'auto_login'
                    }, status=status.HTTP_200_OK)
                    
                except KeyError as e:
                    logger.error(f"Missing key in validated data: {str(e)}")
                    return Response({
                        'success': False,
                        'requires_otp': True,
                        'message': 'Invalid response data'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Handle validation errors
            logger.warning(f"Auto-login validation failed: {serializer.errors}")
            return Response({
                'success': False,
                'requires_otp': True,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)


@method_decorator(csrf_exempt, name='dispatch')
class CheckLoginStatusView(APIView):
    """Check if user can auto-login or needs OTP"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            mobile_number = request.data.get('mobile_number')
            
            if not mobile_number:
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Mobile number required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate mobile number format
            if not mobile_number.isdigit() or len(mobile_number) < 10:
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Invalid mobile number format'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user = User.objects.get(mobile_number=mobile_number)
                
                if user.is_mobile_verified and user.is_auto_login_enabled:
                    # Check if auto-login expired
                    try:
                        thirty_days_ago = timezone.now() - timedelta(days=30)
                        
                        if (user.auto_login_last_used and 
                            user.auto_login_last_used > thirty_days_ago):
                            
                            # Get user name safely
                            user_name = ''
                            try:
                                user_name = user.get_name() if hasattr(user, 'get_name') else ''
                            except Exception as e:
                                logger.error(f"Error getting user name: {str(e)}")
                            
                            return Response({
                                'success': True,
                                'can_auto_login': True,
                                'user_name': user_name,
                                'mobile_number': user.mobile_number,
                                'message': 'You can auto-login'
                            })
                    except Exception as e:
                        logger.error(f"Error checking auto-login expiry: {str(e)}")
                        # If we can't check expiry, require OTP for safety
                        return Response({
                            'success': True,
                            'can_auto_login': False,
                            'requires_otp': True,
                            'message': 'Unable to verify auto-login status. Please use OTP.'
                        })
                
                return Response({
                    'success': True,
                    'can_auto_login': False,
                    'requires_otp': True,
                    'message': 'OTP required for login'
                })
                
            except ObjectDoesNotExist:
                logger.info(f"User not found for login status check: {mobile_number}")
                return Response({
                    'success': True,
                    'can_auto_login': False,
                    'requires_otp': True,
                    'message': 'New user. OTP required for registration.'
                })
            except DatabaseError as e:
                logger.error(f"Database error checking login status: {str(e)}")
                return Response({
                    'success': False,
                    'requires_otp': True,
                    'message': 'Unable to check login status. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            error_response, status_code = handle_exception(e, request)
            return Response(error_response, status=status_code)
        
        

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import User
from .serializers import UserSuggestionSerializer

class MobileNumberSearchView(APIView):
    """
    API endpoint for mobile number autosuggest search
    """
    permission_classes = [IsAuthenticated]  # Adjust based on your needs
    
    def get(self, request):
        query = request.query_params.get('q', '')
        limit = request.query_params.get('limit', 10)
        
        try:
            limit = int(limit)
            if limit > 50:  # Max limit
                limit = 50
        except ValueError:
            limit = 10
        
        if len(query) < 3:  # Minimum characters before searching
            return Response({
                'results': [],
                'message': 'Enter at least 3 characters'
            })
        
        # Search for users with mobile numbers containing the query
        users = User.objects.filter(
            Q(mobile_number__icontains=query) &
            Q(is_active=True)
        ).order_by('mobile_number')[:limit]
        
        serializer = UserSuggestionSerializer(users, many=True)
        
        return Response({
            'results': serializer.data,
            'total': users.count(),
            'query': query
        })

class MobileNumberAutocompleteView(APIView):
    """
    Alternative view optimized for autocomplete components
    Returns simple format for dropdowns
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        query = request.query_params.get('search', '')
        
        if len(query) < 3:
            return Response([])
        
        users = User.objects.filter(
            Q(mobile_number__icontains=query) &
            Q(is_active=True)
        ).values('id', 'mobile_number')[:20]
        
        # Format for autocomplete libraries
        results=[
            {
                'id': user['id'],
                'text': user['mobile_number'],
                'value': user['mobile_number']
            }
            for user in users
        ]
        
        return Response({
            'results': results
        })