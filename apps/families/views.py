from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Family, FamilyInvitation
from .serializers import (
    FamilySerializer,
    FamilyDetailSerializer,
    FamilyInvitationSerializer,
    AcceptInvitationSerializer
)
from apps.genealogy.models import Person

class FamilyViewSet(viewsets.ModelViewSet):
    """ViewSet for Family operations."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return FamilyDetailSerializer
        return FamilySerializer
    
    def get_queryset(self):
        """Get families where user is a member."""
        user = self.request.user
        return Family.objects.filter(
            persons__linked_user=user
        ).distinct().order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create family with user as creator."""
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Invite someone to family."""
        family = self.get_object()
        
        # Check permissions
        if not (request.user == family.created_by or 
                request.user.has_perm('families.invite_members')):
            raise PermissionDenied("You don't have permission to invite members")
        
        serializer = FamilyInvitationSerializer(
            data=request.data,
            context={'request': request, 'family': family}
        )
        
        if serializer.is_valid():
            invitation = serializer.save()
            
            # TODO: Send SMS notification
            # sms_service.send_invitation(
            #     invitation.invitee_mobile,
            #     family.family_name,
            #     invitation.inviter.mobile_number
            # )
            
            return Response({
                'message': 'Invitation sent successfully',
                'invitation_id': invitation.id
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def invitations(self, request):
        """Get user's pending invitations."""
        invitations = FamilyInvitation.objects.filter(
            invitee_mobile=request.user.mobile_number,
            status='pending'
        ).select_related('family', 'inviter')
        
        serializer = FamilyInvitationSerializer(invitations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def accept_invitation(self, request):
        """Accept a family invitation."""
        serializer = AcceptInvitationSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            invitation = serializer.validated_data['invitation']
            
            with transaction.atomic():
                # Accept invitation
                invitation.accept(request.user)
                
                # Add user to family as Person
                if request.user not in invitation.family.get_active_members():
                    Person.objects.create(
                        linked_user=request.user,
                        full_name=request.user.profile.firstname or request.user.mobile_number,
                        gender=request.user.profile.gender,
                        family=invitation.family,
                        date_of_birth=request.user.profile.dateofbirth
                    )
                
                return Response({
                    'message': 'Successfully joined family',
                    'family_id': invitation.family.id,
                    'family_name': invitation.family.family_name
                })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['delete'])
    def leave(self, request, pk=None):
        """Leave a family."""
        family = self.get_object()
        
        # Can't leave if you're the creator and family has other members
        if request.user == family.created_by:
            members_count = family.get_members_count()
            if members_count > 1:
                raise ValidationError(
                    "Family creator cannot leave. Transfer ownership first or delete family."
                )
        
        # Remove user's Person record from family
        Person.objects.filter(
            linked_user=request.user,
            family=family
        ).delete()
        
        return Response({
            'message': 'Successfully left the family'
        }, status=status.HTTP_200_OK)

class FamilyInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing invitations."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FamilyInvitationSerializer
    
    def get_queryset(self):
        """Get invitations sent by user."""
        return FamilyInvitation.objects.filter(
            inviter=self.request.user
        ).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an invitation."""
        invitation = self.get_object()
        
        if invitation.status != 'pending':
            raise ValidationError("Only pending invitations can be cancelled")
        
        invitation.status = 'cancelled'
        invitation.save()
        
        return Response({
            'message': 'Invitation cancelled successfully'
        })