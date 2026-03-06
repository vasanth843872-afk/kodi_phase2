from rest_framework import serializers
from .models import UserProfile
import logging
from datetime import date
from django.core.exceptions import ValidationError as DjangoValidationError

logger = logging.getLogger(__name__)

class PublicProfileSerializer(serializers.ModelSerializer):
    """Serializer for public profile fields (STEP-1 only)."""
    
    class Meta:
        model = UserProfile
        fields = [
            'firstname', 'secondname', 'thirdname',
            'fathername1', 'fathername2',
            'mothername1', 'mothername2',
            'gender', 'preferred_language',
            'religion', 'caste', 'image'
        ]
        read_only_fields = fields
    
    def validate(self, attrs):
        """Validate public profile data."""
        try:
            return super().validate(attrs)
        except Exception as e:
            logger.error(f"Public profile validation error: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Invalid public profile data", "detail": str(e)}
            )


class PrivateProfileSerializer(serializers.ModelSerializer):
    """Serializer for all profile fields (owner only)."""
    
    class Meta:
        model = UserProfile
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def validate(self, attrs):
        """Validate private profile data."""
        try:
            return super().validate(attrs)
        except Exception as e:
            logger.error(f"Private profile validation error: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Invalid private profile data", "detail": str(e)}
            )
    
    def to_representation(self, instance):
        """
        Return full data for owner, public data for others.
        Includes error handling for missing context or user.
        """
        try:
            request = self.context.get('request')
            if not request:
                logger.warning("No request context found in PrivateProfileSerializer")
                return instance.get_public_fields()
            
            if not request.user.is_authenticated:
                return instance.get_public_fields()
            
            if request.user == instance.user:
                return instance.get_private_fields()
            
            return instance.get_public_fields()
            
        except AttributeError as e:
            logger.error(f"User instance error in to_representation: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Invalid user instance", "detail": str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected error in to_representation: {str(e)}")
            # Fallback to public fields in case of error
            try:
                return instance.get_public_fields()
            except:
                raise serializers.ValidationError(
                    {"error": "Failed to serialize profile data"}
                )


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating profile with age auto-calculation."""
    
    # Add explicit field validation if needed
    dateofbirth = serializers.DateField(
        required=False,
        allow_null=True,
        error_messages={
            'invalid': 'Please provide a valid date in YYYY-MM-DD format',
            'null': 'Date of birth cannot be empty if provided'
        }
    )
    
    age = serializers.IntegerField(
        read_only=True,
        required=False,
        help_text="Age is automatically calculated from date of birth"
    )
    
    class Meta:
        model = UserProfile
        fields = [
            # STEP-1
            'firstname', 'secondname', 'thirdname',
            'fathername1', 'fathername2',
            'mothername1', 'mothername2',
            'gender', 'preferred_language',
            'religion', 'caste', 'image',
            # STEP-2
            'dateofbirth', 'age', 'native',
            'present_city', 'taluk', 'district',
            'state', 'contact_number', 'nationality',
            # STEP-3
            'cultureoflife',
            'familyname1', 'familyname2', 'familyname3',
            'familyname4', 'familyname5'
        ]
    
    def validate_dateofbirth(self, value):
        """Validate date of birth is not in the future."""
        try:
            if value and value > date.today():
                raise serializers.ValidationError(
                    "Date of birth cannot be in the future"
                )
            return value
        except Exception as e:
            logger.error(f"Date of birth validation error: {str(e)}")
            raise serializers.ValidationError(
                "Invalid date of birth value"
            )
    
    def validate_contact_number(self, value):
        """Validate contact number format."""
        if value:
            # Add your phone number validation logic here
            # Example: Check if it contains only digits and has valid length
            if not value.isdigit():
                raise serializers.ValidationError(
                    "Contact number should contain only digits"
                )
            if len(value) < 10 or len(value) > 15:
                raise serializers.ValidationError(
                    "Contact number should be between 10 and 15 digits"
                )
        return value
    
    def validate(self, attrs):
        """Cross-field validation."""
        try:
            # Add any cross-field validation rules here
            # Example: If age is provided directly, ensure it matches dob
            if 'age' in attrs and 'dateofbirth' in attrs:
                if attrs['dateofbirth'] and attrs['age']:
                    calculated_age = self._calculate_age(attrs['dateofbirth'])
                    if calculated_age != attrs['age']:
                        logger.warning(f"Age mismatch: provided {attrs['age']}, calculated {calculated_age}")
                        # Uncomment below if you want to enforce consistency
                        # raise serializers.ValidationError({
                        #     "age": "Age does not match date of birth"
                        # })
            
            return super().validate(attrs)
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Profile update validation error: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Invalid profile update data", "detail": str(e)}
            )
    
    def _calculate_age(self, dob):
        """Calculate age from date of birth."""
        if not dob:
            return None
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
    def update(self, instance, validated_data):
        """
        Update profile and auto-calculate age if dateofbirth provided.
        Includes comprehensive error handling and logging.
        """
        try:
            today = date.today()
            
            # Handle date of birth update
            if 'dateofbirth' in validated_data:
                dob = validated_data.get('dateofbirth')
                
                if dob:
                    # Calculate age from new date of birth
                    age = self._calculate_age(dob)
                    validated_data['age'] = age
                    logger.info(f"Age calculated from DOB: {age}")
                else:
                    # If dob is explicitly set to null, set age to null
                    validated_data['age'] = None
                    logger.info("DOB set to null, age set to null")
                    
            # If dateofbirth is not being updated but exists in instance
            elif instance.dateofbirth:
                # Recalculate age based on existing DOB
                age = self._calculate_age(instance.dateofbirth)
                validated_data['age'] = age
                logger.info(f"Age recalculated from existing DOB: {age}")
            
            # Perform the update
            updated_instance = super().update(instance, validated_data)
            logger.info(f"Profile updated successfully for user: {updated_instance.user}")
            
            return updated_instance
            
        except DjangoValidationError as e:
            logger.error(f"Django validation error during profile update: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Database validation failed", "detail": str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected error during profile update: {str(e)}", exc_info=True)
            raise serializers.ValidationError(
                {"error": "Failed to update profile", "detail": "An unexpected error occurred"}
            )
    
    def save(self, **kwargs):
        """Override save with error handling."""
        try:
            return super().save(**kwargs)
        except Exception as e:
            logger.error(f"Error saving profile: {str(e)}")
            raise serializers.ValidationError(
                {"error": "Failed to save profile", "detail": str(e)}
            )