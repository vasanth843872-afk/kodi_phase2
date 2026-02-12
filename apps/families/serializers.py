from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
import secrets
from .models import Family, FamilyInvitation
from apps.genealogy.models import Person

class FamilySerializer(serializers.ModelSerializer):
    """Serializer for Family model."""
    
    members_count = serializers.IntegerField(source='get_members_count', read_only=True)
    created_by_name = serializers.CharField(source='created_by.mobile_number', read_only=True)
    
    class Meta:
        model = Family
        fields = [
            'id', 'family_name', 'description', 'is_locked',
            'created_by', 'created_by_name', 'members_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Create family and add creator as member."""
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        
        family = super().create(validated_data)
        
        # Create Person record for creator
        Person.objects.create(
            linked_user=request.user,
            full_name=request.user.profile.firstname or request.user.mobile_number,
            gender=request.user.profile.gender,
            family=family,
            date_of_birth=request.user.profile.dateofbirth
        )
        
        return family

class FamilyDetailSerializer(FamilySerializer):
    """Detailed family serializer with members."""
    
    members = serializers.SerializerMethodField()
    
    class Meta(FamilySerializer.Meta):
        fields = FamilySerializer.Meta.fields + ['members']
    
    def get_members(self, obj):
        """Get family members with public profile info."""
        members = Person.objects.filter(family=obj).select_related(
            'linked_user', 'linked_user__profile'
        )[:100]  # Limit for performance
        
        return [
            {
                'person_id': member.id,
                'user_id': member.linked_user.id if member.linked_user else None,
                'full_name': member.full_name,
                'gender': member.gender,
                'public_profile': member.get_public_profile() if member.linked_user else None
            }
            for member in members
        ]

class FamilyInvitationSerializer(serializers.ModelSerializer):
    """Serializer for family invitations."""
    
    family_name = serializers.CharField(source='family.family_name', read_only=True)
    inviter_mobile = serializers.CharField(source='inviter.mobile_number', read_only=True)
    
    class Meta:
        model = FamilyInvitation
        fields = [
            'id', 'family', 'family_name', 'inviter', 'inviter_mobile',
            'invitee_mobile', 'invitee_user', 'status',
            'created_at', 'expires_at'
        ]
        read_only_fields = ['inviter', 'invitation_token', 'created_at', 'expires_at']
    
    def validate_invitee_mobile(self, value):
        """Validate invitee mobile number."""
        request = self.context.get('request')
        if value == request.user.mobile_number:
            raise serializers.ValidationError("Cannot invite yourself")
        return value
    
    def create(self, validated_data):
        """Create invitation with token and expiry."""
        request = self.context.get('request')
        validated_data['inviter'] = request.user
        validated_data['family'] = self.context.get('family')
        
        # Generate unique token
        validated_data['invitation_token'] = secrets.token_urlsafe(32)
        
        # Set expiry (7 days)
        validated_data['expires_at'] = timezone.now() + timedelta(days=7)
        
        # Check if user exists
        from apps.accounts.models import User
        try:
            user = User.objects.get(mobile_number=validated_data['invitee_mobile'])
            validated_data['invitee_user'] = user
        except User.DoesNotExist:
            validated_data['invitee_user'] = None
        
        return super().create(validated_data)

class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting invitation."""
    token = serializers.CharField(required=True)
    
    def validate(self, data):
        token = data['token']
        request = self.context.get('request')
        
        try:
            invitation = FamilyInvitation.objects.get(
                invitation_token=token,
                status='pending'
            )
        except FamilyInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired invitation")
        
        if invitation.is_expired():
            invitation.status = 'expired'
            invitation.save()
            raise serializers.ValidationError("Invitation has expired")
        
        if invitation.invitee_user and invitation.invitee_user != request.user:
            raise serializers.ValidationError("This invitation is for another user")
        
        data['invitation'] = invitation
        return data