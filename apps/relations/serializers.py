from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from django.db import IntegrityError
import logging
from typing import Dict, Any, Optional, List
from .models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily

# Configure logger
logger = logging.getLogger(__name__)

class BaseRelationSerializer(serializers.ModelSerializer):
    """Base serializer with common functionality for relation serializers."""
    
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Common validation for all relation serializers."""
        try:
            # Check for duplicate entries
            if self.instance is None:  # Only for create operations
                model_class = self.Meta.model
                relation = attrs.get('relation')
                
                # Build unique together fields based on model
                unique_fields = ['relation']
                if hasattr(model_class, 'language'):
                    unique_fields.append('language')
                if hasattr(model_class, 'religion'):
                    unique_fields.append('religion')
                if hasattr(model_class, 'caste'):
                    unique_fields.append('caste')
                if hasattr(model_class, 'family_name'):
                    unique_fields.append('family_name')
                
                filter_kwargs = {field: attrs.get(field) for field in unique_fields}
                
                if model_class.objects.filter(**filter_kwargs).exists():
                    field_names = ', '.join(unique_fields)
                    raise serializers.ValidationError(
                        f"Record with this combination of {field_names} already exists."
                    )
            
            return attrs
            
        except Exception as e:
            logger.error(f"Validation error in {self.__class__.__name__}: {str(e)}")
            raise serializers.ValidationError(f"Validation failed: {str(e)}")
    
    def create(self, validated_data: Dict[str, Any]) -> Any:
        """Create with error handling."""
        try:
            return super().create(validated_data)
        except IntegrityError as e:
            logger.error(f"Integrity error in {self.__class__.__name__} create: {str(e)}")
            raise serializers.ValidationError("A record with these details already exists.")
        except Exception as e:
            logger.error(f"Unexpected error in {self.__class__.__name__} create: {str(e)}")
            raise serializers.ValidationError(f"Failed to create record: {str(e)}")
    
    def update(self, instance: Any, validated_data: Dict[str, Any]) -> Any:
        """Update with error handling."""
        try:
            return super().update(instance, validated_data)
        except Exception as e:
            logger.error(f"Error in {self.__class__.__name__} update: {str(e)}")
            raise serializers.ValidationError(f"Failed to update record: {str(e)}")


class FixedRelationSerializer(serializers.ModelSerializer):
    """Serializer for FixedRelation model with enhanced error handling."""
    
    display_name = serializers.SerializerMethodField()
    validation_status = serializers.SerializerMethodField()
    
    class Meta:
        model = FixedRelation
        fields = [
            'id', 'relation_code', 'display_name', 'category',
            'default_english', 'default_tamil', 'gender_specific',
            'allowed_from_gender', 'allowed_to_gender', 'validation_status',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'relation_code': {
                'required': True,
                'allow_blank': False,
                'help_text': 'Unique code for the relation'
            },
            'category': {
                'required': True,
                'help_text': 'Category of the relation'
            }
        }
    
    def validate_relation_code(self, value: str) -> str:
        """Validate relation code format."""
        if not value or not value.strip():
            raise serializers.ValidationError("Relation code cannot be empty.")
        
        # Check for valid characters (alphanumeric and underscore only)
        if not value.replace('_', '').isalnum():
            raise serializers.ValidationError(
                "Relation code can only contain letters, numbers, and underscores."
            )
        
        # Check uniqueness for new records
        if not self.instance and FixedRelation.objects.filter(relation_code=value).exists():
            raise serializers.ValidationError(f"Relation code '{value}' already exists.")
        
        return value.upper()  # Store in uppercase for consistency
    
    def validate_category(self, value: str) -> str:
        """Validate category."""
        valid_categories = ['family', 'social', 'professional', 'other']
        if value and value.lower() not in valid_categories:
            raise serializers.ValidationError(
                f"Category must be one of: {', '.join(valid_categories)}"
            )
        return value.lower() if value else value
    
    def get_display_name(self, obj: FixedRelation) -> str:
        """Get localized display name with fallback."""
        try:
            request = self.context.get('request')
            
            # Get language from request
            language = 'en'  # default
            religion = ''
            caste = ''
            family = ''
            
            if request:
                # Get language from query param or user profile
                language = request.query_params.get('lang', 'en')
                
                # Get user context for better localization
                if hasattr(request, 'user') and request.user and not request.user.is_anonymous:
                    try:
                        if hasattr(request.user, 'profile'):
                            profile = request.user.profile
                            language = getattr(profile, 'preferred_language', language)
                            religion = getattr(profile, 'religion', '')
                            caste = getattr(profile, 'caste', '')
                            
                            # Get family from user's person record
                            if hasattr(request.user, 'person_record') and request.user.person_record:
                                if hasattr(request.user.person_record, 'family') and request.user.person_record.family:
                                    family = request.user.person_record.family.family_name
                    except Exception as e:
                        logger.warning(f"Error getting user profile context: {str(e)}")
            
            # Get localized name with fallback
            return obj.get_localized_name(
                language=language,
                religion=religion,
                caste=caste,
                family=family
            )
            
        except Exception as e:
            logger.error(f"Error getting display name for relation {obj.relation_code}: {str(e)}")
            # Return default English name as fallback
            return obj.default_english
    
    def get_validation_status(self, obj: FixedRelation) -> Dict[str, Any]:
        """Get validation status for gender combinations."""
        try:
            return {
                'is_valid': obj.validate_gender_combination(),
                'allowed_from_gender': obj.allowed_from_gender,
                'allowed_to_gender': obj.allowed_to_gender,
                'is_gender_specific': obj.gender_specific
            }
        except Exception as e:
            logger.error(f"Error getting validation status: {str(e)}")
            return {'is_valid': False, 'error': str(e)}


class RelationLanguageReligionSerializer(BaseRelationSerializer):
    """Serializer for RelationLanguageReligion with comprehensive error handling."""
    
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationLanguageReligion
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'relation': {'required': True},
            'language': {'required': True, 'max_length': 10},
            'religion': {'required': True, 'max_length': 100},
            'label': {'required': True, 'allow_blank': False}
        }
    
    def validate_language(self, value: str) -> str:
        """Validate language code."""
        if not value or len(value) < 2:
            raise serializers.ValidationError("Language code must be at least 2 characters.")
        
        # List of supported languages (can be moved to settings)
        supported_languages = ['en', 'ta', 'hi', 'te', 'ml', 'kn']
        if value.lower() not in supported_languages:
            raise serializers.ValidationError(
                f"Language '{value}' is not supported. Supported languages: {', '.join(supported_languages)}"
            )
        
        return value.lower()
    
    def validate_religion(self, value: str) -> str:
        """Validate religion."""
        if not value or not value.strip():
            raise serializers.ValidationError("Religion cannot be empty.")
        return value.strip()
    
    def validate_label(self, value: str) -> str:
        """Validate label."""
        if not value or not value.strip():
            raise serializers.ValidationError("Label cannot be empty.")
        return value.strip()


class RelationCasteSerializer(BaseRelationSerializer):
    """Serializer for RelationCaste with comprehensive error handling."""
    
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationCaste
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'relation': {'required': True},
            'caste': {'required': True, 'max_length': 100},
            'label': {'required': True, 'allow_blank': False}
        }
    
    def validate_caste(self, value: str) -> str:
        """Validate caste."""
        if not value or not value.strip():
            raise serializers.ValidationError("Caste cannot be empty.")
        return value.strip()
    
    def validate_label(self, value: str) -> str:
        """Validate label."""
        if not value or not value.strip():
            raise serializers.ValidationError("Label cannot be empty.")
        return value.strip()


class RelationFamilySerializer(BaseRelationSerializer):
    """Serializer for RelationFamily with comprehensive error handling."""
    
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationFamily
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'relation': {'required': True},
            'family_name': {'required': True, 'max_length': 100},
            'label': {'required': True, 'allow_blank': False}
        }
    
    def validate_family_name(self, value: str) -> str:
        """Validate family name."""
        if not value or not value.strip():
            raise serializers.ValidationError("Family name cannot be empty.")
        return value.strip()
    
    def validate_label(self, value: str) -> str:
        """Validate label."""
        if not value or not value.strip():
            raise serializers.ValidationError("Label cannot be empty.")
        return value.strip()


class RelationLabelRequestSerializer(serializers.Serializer):
    """Serializer for requesting relation labels with enhanced validation."""
    
    relation_code = serializers.CharField(required=True, max_length=50)
    language = serializers.CharField(required=True, max_length=10)
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    family_name = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate_relation_code(self, value: str) -> str:
        """Validate relation code exists."""
        try:
            if not FixedRelation.objects.filter(relation_code=value).exists():
                raise serializers.ValidationError(
                    f"Relation code '{value}' does not exist."
                )
            return value
        except Exception as e:
            logger.error(f"Error validating relation code: {str(e)}")
            raise serializers.ValidationError(f"Invalid relation code: {str(e)}")
    
    def validate_language(self, value: str) -> str:
        """Validate language code."""
        supported_languages = ['en', 'ta', 'hi', 'te', 'ml', 'kn']
        if value.lower() not in supported_languages:
            raise serializers.ValidationError(
                f"Language '{value}' is not supported. Supported languages: {', '.join(supported_languages)}"
            )
        return value.lower()
    
    def validate_religion(self, value: str) -> str:
        """Validate religion."""
        if not value or not value.strip():
            raise serializers.ValidationError("Religion cannot be empty.")
        return value.strip()
    
    def validate_caste(self, value: str) -> str:
        """Validate caste."""
        if not value or not value.strip():
            raise serializers.ValidationError("Caste cannot be empty.")
        return value.strip()
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-field validation."""
        try:
            # Check if any combination exists
            from .models import RelationLanguageReligion, RelationCaste, RelationFamily
            
            relation = FixedRelation.objects.get(relation_code=data['relation_code'])
            
            # Log the lookup attempt
            logger.debug(f"Validating label request for relation: {relation.relation_code}")
            
            return data
            
        except FixedRelation.DoesNotExist:
            raise serializers.ValidationError(f"Relation not found: {data.get('relation_code')}")
        except Exception as e:
            logger.error(f"Error in relation label request validation: {str(e)}")
            raise serializers.ValidationError(f"Validation failed: {str(e)}")


class BulkRelationLabelsSerializer(serializers.Serializer):
    """Serializer for bulk relation label requests with enhanced validation."""
    
    language = serializers.CharField(required=True, max_length=10)
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    family_name = serializers.CharField(required=False, allow_blank=True, default='')
    relation_codes = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=[]
    )
    
    def validate_language(self, value: str) -> str:
        """Validate language code."""
        supported_languages = ['en', 'ta', 'hi', 'te', 'ml', 'kn']
        if value.lower() not in supported_languages:
            raise serializers.ValidationError(
                f"Language '{value}' is not supported. Supported languages: {', '.join(supported_languages)}"
            )
        return value.lower()
    
    def validate_religion(self, value: str) -> str:
        """Validate religion."""
        if not value or not value.strip():
            raise serializers.ValidationError("Religion cannot be empty.")
        return value.strip()
    
    def validate_caste(self, value: str) -> str:
        """Validate caste."""
        if not value or not value.strip():
            raise serializers.ValidationError("Caste cannot be empty.")
        return value.strip()
    
    def validate_relation_codes(self, value: List[str]) -> List[str]:
        """Validate relation codes list."""
        if value:
            # Check for duplicates
            if len(value) != len(set(value)):
                raise serializers.ValidationError("Duplicate relation codes are not allowed.")
            
            # Validate each code exists
            existing_codes = set(FixedRelation.objects.filter(
                relation_code__in=value
            ).values_list('relation_code', flat=True))
            
            invalid_codes = set(value) - existing_codes
            if invalid_codes:
                raise serializers.ValidationError(
                    f"Invalid relation codes: {', '.join(invalid_codes)}"
                )
        
        return value


class GenderValidationSerializer(serializers.Serializer):
    """Serializer for gender validation with enhanced error handling."""
    
    relation_code = serializers.CharField(required=True, max_length=50)
    from_gender = serializers.ChoiceField(
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        required=True
    )
    to_gender = serializers.ChoiceField(
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        required=True
    )
    
    def validate_relation_code(self, value: str) -> str:
        """Validate relation code exists."""
        try:
            if not FixedRelation.objects.filter(relation_code=value).exists():
                raise serializers.ValidationError(
                    f"Relation code '{value}' does not exist."
                )
            return value
        except Exception as e:
            logger.error(f"Error validating relation code: {str(e)}")
            raise serializers.ValidationError(f"Invalid relation code: {str(e)}")
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-field validation for gender combination."""
        try:
            relation = FixedRelation.objects.get(relation_code=data['relation_code'])
            
            # Check if the relation supports this gender combination
            if relation.gender_specific:
                if data['from_gender'] not in relation.allowed_from_gender:
                    raise serializers.ValidationError(
                        f"From gender '{data['from_gender']}' is not allowed for this relation. "
                        f"Allowed from genders: {relation.allowed_from_gender}"
                    )
                
                if data['to_gender'] not in relation.allowed_to_gender:
                    raise serializers.ValidationError(
                        f"To gender '{data['to_gender']}' is not allowed for this relation. "
                        f"Allowed to genders: {relation.allowed_to_gender}"
                    )
            
            return data
            
        except FixedRelation.DoesNotExist:
            raise serializers.ValidationError(f"Relation not found: {data.get('relation_code')}")
        except Exception as e:
            logger.error(f"Error in gender validation: {str(e)}")
            raise serializers.ValidationError(f"Gender validation failed: {str(e)}")


# Utility function to handle serializer errors
def handle_serializer_errors(serializer: serializers.Serializer) -> Dict[str, Any]:
    """
    Utility function to format serializer errors consistently.
    """
    if serializer.is_valid():
        return {'success': True, 'data': serializer.validated_data}
    
    errors = {}
    for field, field_errors in serializer.errors.items():
        errors[field] = [str(error) for error in field_errors]
    
    logger.warning(f"Serializer validation failed: {errors}")
    
    return {
        'success': False,
        'errors': errors,
        'message': 'Validation failed. Please check the provided data.'
    }