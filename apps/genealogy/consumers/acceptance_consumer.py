import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from apps.genealogy.models import Invitation, Person, PersonRelation

logger = logging.getLogger(__name__)

class InvitationAcceptanceConsumer(AsyncWebsocketConsumer):
    """
    Dedicated WebSocket consumer for real-time invitation acceptance flow
    """
    
    async def connect(self):
        """Connect to invitation acceptance room"""
        self.user = self.scope["user"]
        self.invitation_token = self.scope['url_route']['kwargs'].get('token')
        
        # Reject unauthenticated
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        
        # Verify invitation belongs to user
        is_valid = await self.verify_invitation()
        if not is_valid:
            await self.close(code=4002, reason="Invalid or expired invitation")
            return
        
        self.room_group_name = f"invitation_acceptance_{self.invitation_token}"
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to acceptance flow for invitation {self.invitation_token}")
        
        # Send invitation details
        await self.send_invitation_details()
    
    async def disconnect(self, close_code):
        """Leave acceptance room"""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle messages in acceptance flow"""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            handlers = {
                'accept': self.handle_accept,
                'reject': self.handle_reject,
                'get_status': self.send_invitation_details,
                'confirm_accept': self.handle_confirm_accept
            }
            
            handler = handlers.get(action)
            if handler:
                await handler(data)
            else:
                await self.send_error(f"Unknown action: {action}")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            logger.error(f"Error in acceptance consumer: {str(e)}", exc_info=True)
            await self.send_error(str(e))
    
    async def handle_accept(self, data):
        """Handle accept action - show confirmation step"""
        invitation = await self.get_invitation()
        if not invitation:
            await self.send_error("Invitation not found")
            return
        
        await self.send(text_data=json.dumps({
            'type': 'show_confirmation',
            'invitation': invitation,
            'message': f'Are you sure you want to accept being {invitation["person"]["name"]}?',
            'timestamp': timezone.now().isoformat()
        }))
    
    async def handle_confirm_accept(self, data):
        """Handle confirmed acceptance"""
        result = await self.process_acceptance()
        
        if result['success']:
            await self.send(text_data=json.dumps({
                'type': 'acceptance_complete',
                'person': result['person'],
                'message': f"✅ Success! You are now connected as {result['person']['name']}",
                'redirect_url': f"/family/tree/?person={result['person']['id']}",
                'timestamp': timezone.now().isoformat()
            }))
            
            # Notify inviter
            await self.notify_inviter(result)
        else:
            await self.send_error(result['message'])
    
    async def handle_reject(self, data):
        """Handle rejection"""
        result = await self.reject_invitation()
        
        if result['success']:
            await self.send(text_data=json.dumps({
                'type': 'rejection_complete',
                'message': 'Invitation rejected',
                'redirect_url': '/family/',
                'timestamp': timezone.now().isoformat()
            }))
        else:
            await self.send_error(result['message'])
    
    async def send_invitation_details(self):
        """Send invitation details to client"""
        invitation = await self.get_invitation()
        if invitation:
            await self.send(text_data=json.dumps({
                'type': 'invitation_details',
                'invitation': invitation,
                'timestamp': timezone.now().isoformat()
            }))
        else:
            await self.send_error("Invitation not found")
    
    async def send_error(self, message):
        """Send error message"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))
    
    async def notify_inviter(self, acceptance_data):
        """Notify inviter of acceptance"""
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            
            await channel_layer.group_send(
                f"user_{acceptance_data['inviter_id']}_invitations",
                {
                    'type': 'invitation_accepted',
                    'invitation': {
                        'id': acceptance_data['invitation_id'],
                        'person_id': acceptance_data['person']['id'],
                        'person_name': acceptance_data['person']['name'],
                        'accepted_by': self.user.id,
                        'accepted_by_name': self.get_user_display_name(self.user)
                    },
                    'message': f'🎉 {self.get_user_display_name(self.user)} accepted your invitation!',
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error notifying inviter: {str(e)}")
    
    @database_sync_to_async
    def verify_invitation(self):
        """Verify invitation token belongs to current user"""
        try:
            invitation = Invitation.objects.get(
                token=self.invitation_token,
                invited_user=self.user,
                status='pending'
            )
            return not invitation.is_expired()
        except Invitation.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_invitation(self):
        """Get invitation details"""
        try:
            invitation = Invitation.objects.select_related(
                'person', 'invited_by', 'invited_by__profile', 'original_relation'
            ).get(
                token=self.invitation_token,
                invited_user=self.user
            )
            
            if invitation.is_expired():
                return None
                
            return {
                'id': invitation.id,
                'token': invitation.token,
                'person': {
                    'id': invitation.person.id,
                    'name': invitation.person.full_name,
                    'gender': invitation.person.gender,
                    'original_name': invitation.person.original_name,
                    'is_placeholder': invitation.person.is_placeholder
                },
                'invited_by': {
                    'id': invitation.invited_by.id,
                    'name': self.get_user_display_name(invitation.invited_by),
                    'mobile_number': invitation.invited_by.mobile_number
                },
                'original_relation': invitation.original_relation.relation_code if invitation.original_relation else None,
                'placeholder_gender': invitation.placeholder_gender,
                'created_at': invitation.created_at.isoformat(),
                'expires_at': invitation.expires_at.isoformat() if invitation.expires_at else None,
                'status': invitation.status
            }
        except Invitation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def process_acceptance(self):
        """Process invitation acceptance"""
        from django.db import transaction
        
        try:
            with transaction.atomic():
                invitation = Invitation.objects.select_for_update().get(
                    token=self.invitation_token,
                    invited_user=self.user,
                    status='pending'
                )
                
                if invitation.is_expired():
                    invitation.status = 'expired'
                    invitation.save()
                    return {
                        'success': False,
                        'message': 'Invitation has expired'
                    }
                
                # Get or create user's person
                user_person = Person.objects.filter(linked_user=self.user).first()
                placeholder = invitation.person
                inviter_person = Person.objects.filter(
                    linked_user=invitation.invited_by
                ).first()
                
                # Process acceptance
                if user_person:
                    # Transfer relations
                    user_person.outgoing_relations.all().update(from_person=placeholder)
                    user_person.incoming_relations.all().update(to_person=placeholder)
                    user_person.delete()
                
                # Link user to placeholder
                placeholder.linked_user = self.user
                placeholder.is_placeholder = False
                
                # Update name if needed
                display_name = self.get_user_display_name(self.user)
                if placeholder.full_name != display_name:
                    placeholder.original_name = placeholder.full_name
                    placeholder.full_name = display_name
                
                placeholder.save()
                
                # Confirm all pending relations
                PersonRelation.objects.filter(
                    Q(from_person=placeholder) | Q(to_person=placeholder),
                    status='pending'
                ).update(status='confirmed')
                
                # Create connection to inviter if needed
                if inviter_person and invitation.original_relation:
                    existing = PersonRelation.objects.filter(
                        Q(from_person=placeholder, to_person=inviter_person) |
                        Q(from_person=inviter_person, to_person=placeholder)
                    ).first()
                    
                    if not existing:
                        PersonRelation.objects.create(
                            from_person=placeholder,
                            to_person=inviter_person,
                            relation=invitation.original_relation,
                            status='confirmed',
                            created_by=self.user
                        )
                
                # Update invitation
                invitation.status = 'accepted'
                invitation.accepted_at = timezone.now()
                invitation.save()
                
                return {
                    'success': True,
                    'invitation_id': invitation.id,
                    'inviter_id': invitation.invited_by.id if invitation.invited_by else None,
                    'person': {
                        'id': placeholder.id,
                        'name': placeholder.full_name,
                        'gender': placeholder.gender
                    }
                }
                
        except Invitation.DoesNotExist:
            return {
                'success': False,
                'message': 'Invitation not found'
            }
        except Exception as e:
            logger.error(f"Error processing acceptance: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    @database_sync_to_async
    def reject_invitation(self):
        """Reject invitation"""
        try:
            invitation = Invitation.objects.get(
                token=self.invitation_token,
                invited_user=self.user,
                status='pending'
            )
            
            invitation.status = 'rejected'
            invitation.resolved_at = timezone.now()
            invitation.save()
            
            return {
                'success': True,
                'invitation_id': invitation.id,
                'inviter_id': invitation.invited_by.id if invitation.invited_by else None
            }
            
        except Invitation.DoesNotExist:
            return {
                'success': False,
                'message': 'Invitation not found'
            }
    
    def get_user_display_name(self, user):
        """Get user's display name"""
        try:
            if hasattr(user, 'profile') and user.profile.firstname:
                return user.profile.firstname.strip()
            elif user.mobile_number:
                return user.mobile_number
            else:
                return f"User_{user.id}"
        except:
            return f"User_{user.id}"