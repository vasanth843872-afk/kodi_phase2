from rest_framework import serializers
from .models import UserProfile

class PublicProfileSerializer(serializers.ModelSerializer):
    """Serializer for public profile fields (STEP-1 only)."""
    
    class Meta:
        model = UserProfile
        fields = [
            'firstname', 'secondname', 'thirdname',
            'fathername1', 'fathername2',
            'mothername1', 'mothername2',
            'gender', 'preferred_language',
            'religion', 'caste','image'
        ]
        read_only_fields = fields

class PrivateProfileSerializer(serializers.ModelSerializer):
    """Serializer for all profile fields (owner only)."""
    
    class Meta:
        model = UserProfile
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Return full data for owner, public data for others."""
        request = self.context.get('request')
        if request and request.user == instance.user:
            return instance.get_private_fields()
        return instance.get_public_fields()
    

class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating profile."""
    
    class Meta:
        model = UserProfile
        fields = [
            # STEP-1
            'firstname', 'secondname', 'thirdname',
            'fathername1', 'fathername2',
            'mothername1', 'mothername2',
            'gender', 'preferred_language',
            'religion', 'caste','image',
            # STEP-2
            'dateofbirth', 'age', 'native',
            'present_city', 'taluk', 'district',
            'state', 'contact_number', 'nationality',
            # STEP-3
            'cultureoflife',
            'familyname1', 'familyname2', 'familyname3',
            'familyname4', 'familyname5'
        ]
    
    def update(self, instance, validated_data):
        """Update profile and auto-calculate age if dateofbirth provided."""
        if 'dateofbirth' in validated_data:
            from datetime import date
            today = date.today()
            dob = validated_data['dateofbirth']
            if dob:
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                validated_data['age'] = age
            else:
            # If dob is explicitly set to null, set age to null
             validated_data['age'] = None
             
        else:
        # If dateofbirth is not being updated, keep existing value
        # But recalculate age if dateofbirth exists
            if instance.dateofbirth:
                dob = instance.dateofbirth
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                validated_data['age'] = age
        return super().update(instance, validated_data)