from rest_framework import serializers
from .models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily

from rest_framework import serializers
from .models import FixedRelation

class FixedRelationSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = FixedRelation
        fields = ['id', 'relation_code', 'display_name', 'category']
    
    def get_display_name(self, obj):
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
            if hasattr(request.user, 'profile'):
                profile = request.user.profile
                language = getattr(profile, 'preffered_language', language)
                religion = getattr(profile, 'religion', '')
                caste = getattr(profile, 'caste', '')
                
                # Get family from user's person record
                if hasattr(request.user, 'person_record'):
                    family = request.user.person_record.family.family_name
        
        # Use the new method
        return obj.get_localized_name(
            language=language,
            religion=religion,
            caste=caste,
            family=family
        )

class RelationLanguageReligionSerializer(serializers.ModelSerializer):
    """Serializer for RelationLanguageReligion."""
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationLanguageReligion
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class RelationCasteSerializer(serializers.ModelSerializer):
    """Serializer for RelationCaste."""
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationCaste
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class RelationFamilySerializer(serializers.ModelSerializer):
    """Serializer for RelationFamily."""
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    default_english = serializers.CharField(source='relation.default_english', read_only=True)
    default_tamil = serializers.CharField(source='relation.default_tamil', read_only=True)
    
    class Meta:
        model = RelationFamily
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class RelationLabelRequestSerializer(serializers.Serializer):
    """Serializer for requesting relation labels."""
    relation_code = serializers.CharField(required=True)
    language = serializers.CharField(required=True, max_length=10)
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    family_name = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        from .models import FixedRelation
        if not FixedRelation.objects.filter(relation_code=data['relation_code']).exists():
            raise serializers.ValidationError(f"Invalid relation code: {data['relation_code']}")
        return data

class BulkRelationLabelsSerializer(serializers.Serializer):
    """Serializer for bulk relation label requests."""
    language = serializers.CharField(required=True, max_length=10)
    religion = serializers.CharField(required=True, max_length=100)
    caste = serializers.CharField(required=True, max_length=100)
    family_name = serializers.CharField(required=False, allow_blank=True)
    relation_codes = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False
    )

class GenderValidationSerializer(serializers.Serializer):
    """Serializer for gender validation."""
    relation_code = serializers.CharField(required=True)
    from_gender = serializers.ChoiceField(choices=['M', 'F', 'O'], required=True)
    to_gender = serializers.ChoiceField(choices=['M', 'F', 'O'], required=True)