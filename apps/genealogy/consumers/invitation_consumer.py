import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.genealogy.models import Invitation, Person, PersonRelation
from apps.relations.models import FixedRelation

logger = logging.getLogger(__name__)
User = get_user_model()

class InvitationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time invitation notifications and acceptance
    """
    
    async def connect(self):
        """Connect user to their personal invitation channel"""
        self.user = self.scope["user"]
        
        # Reject unauthenticated connections
        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Rejected unauthenticated WebSocket connection")
            await self.close(code=4001)
            return
        
        # Create unique room for this user
        self.room_group_name = f"user_{self.user.id}_invitations"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to invitation WebSocket")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to invitation service',
            'user_id': self.user.id,
            'timestamp': timezone.now().isoformat()
        }))
        
        # Send any pending invitations
        await self.send_pending_invitations()
    
    async def disconnect(self, close_code):
        """Leave room group"""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.id} disconnected from invitation WebSocket")
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            handlers = {
                'get_pending_invitations': self.handle_get_pending,
                'invitation_response': self.handle_invitation_response,
                'mark_seen': self.handle_mark_seen,
                'ping': self.handle_ping,
                'get_invitation_details': self.handle_get_invitation_details
            }
            
            handler = handlers.get(message_type)
            if handler:
                await handler(data)
            else:
                await self.send_error(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)
            await self.send_error(f"Internal error: {str(e)}")
    
    # In your invitation_consumer.py, in the invitation_notification method
    # Make sure you're not using expires_at

    async def invitation_notification(self, event):
        """
        Send new invitation notification to user
        """
        invitation = event['invitation']
        
        await self.send(text_data=json.dumps({
            'type': 'new_invitation',
            'invitation': {
                'id': invitation['id'],
                'token': invitation['token'],
                'person': invitation['person'],
                'invited_by': invitation['invited_by'],
                'original_relation': invitation.get('original_relation'),
                'placeholder_gender': invitation.get('placeholder_gender'),
                'created_at': invitation.get('created_at')
                # Don't include expires_at
            },
            'message': event['message']
        }))
    
    async def invitation_accepted(self, event):
        """Notify inviter that invitation was accepted"""
        await self.send(text_data=json.dumps({
            'type': 'invitation_accepted',
            'invitation': event['invitation'],
            'message': event['message'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def invitation_rejected(self, event):
        """Notify inviter that invitation was rejected"""
        await self.send(text_data=json.dumps({
            'type': 'invitation_rejected',
            'invitation': event['invitation'],
            'message': event['message'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def invitation_expired(self, event):
        """Notify about expired invitation"""
        await self.send(text_data=json.dumps({
            'type': 'invitation_expired',
            'invitation': event['invitation'],
            'message': event['message'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def handle_get_pending(self, data):
        """Handle request for pending invitations"""
        await self.send_pending_invitations()
    
    async def handle_ping(self, data):
        """Respond to ping to keep connection alive"""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': timezone.now().isoformat()
        }))
    
    async def handle_get_invitation_details(self, data):
        """Get details for a specific invitation"""
        invitation_id = data.get('invitation_id')
        token = data.get('token')
        
        invitation_data = await self.get_invitation_details(invitation_id, token)
        if invitation_data:
            await self.send(text_data=json.dumps({
                'type': 'invitation_details',
                'invitation': invitation_data,
                'timestamp': timezone.now().isoformat()
            }))
        else:
            await self.send_error("Invitation not found")
    
    async def handle_invitation_response(self, data):
        """Handle user's response to invitation"""
        invitation_id = data.get('invitation_id')
        token = data.get('token')
        response = data.get('response')  # 'accept', 'reject', or 'later'
        
        if response not in ['accept', 'reject', 'later']:
            await self.send_error("Invalid response type")
            return
        
        try:
            result = await self.process_invitation_response(
                invitation_id, token, response
            )
            
            if result['success']:
                if response == 'accept':
                    await self.send(text_data=json.dumps({
                        'type': 'acceptance_confirmed',
                        'invitation_id': result['invitation_id'],
                        'person': result['person'],
                        'message': f"✅ You are now connected as {result['person']['name']}!",
                        'redirect': f"/family/tree/?person={result['person']['id']}",
                        'timestamp': timezone.now().isoformat()
                    }))
                    
                    # Notify inviter
                    if result.get('inviter_id'):
                        await self.notify_inviter(result)
                        
                elif response == 'reject':
                    await self.send(text_data=json.dumps({
                        'type': 'rejection_confirmed',
                        'invitation_id': result['invitation_id'],
                        'message': 'Invitation rejected',
                        'timestamp': timezone.now().isoformat()
                    }))
                    
                    # Notify inviter
                    if result.get('inviter_id'):
                        await self.notify_inviter_rejected(result)
                        
                else:  # later
                    await self.send(text_data=json.dumps({
                        'type': 'dismissed',
                        'invitation_id': result['invitation_id'],
                        'message': 'You can accept later from your invitations panel',
                        'timestamp': timezone.now().isoformat()
                    }))
            else:
                await self.send_error(result['message'])
                
        except Exception as e:
            logger.error(f"Error processing invitation response: {str(e)}", exc_info=True)
            await self.send_error(f"Failed to process response: {str(e)}")
    
    async def handle_mark_seen(self, data):
        """Mark invitations as seen"""
        invitation_ids = data.get('invitation_ids', [])
        if invitation_ids:
            await self.mark_invitations_seen(invitation_ids)
    
    async def send_pending_invitations(self):
        """Send all pending invitations to the user"""
        try:
            invitations = await self.get_pending_invitations()
            
            if invitations:
                await self.send(text_data=json.dumps({
                    'type': 'pending_invitations',
                    'invitations': invitations,
                    'count': len(invitations),
                    'dialog': {
                        'title': f'📨 You have {len(invitations)} pending invitation(s)',
                        'show_dialog': len(invitations) > 0
                    },
                    'timestamp': timezone.now().isoformat()
                }))
                
                # Update notification badge count
                await self.send(text_data=json.dumps({
                    'type': 'badge_update',
                    'count': len(invitations),
                    'timestamp': timezone.now().isoformat()
                }))
                
        except Exception as e:
            logger.error(f"Error sending pending invitations: {str(e)}", exc_info=True)
    
    async def notify_inviter(self, acceptance_data):
        """Notify inviter that their invitation was accepted"""
        try:
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
                    'message': f'🎉 {self.get_user_display_name(self.user)} accepted your invitation to be {acceptance_data["person"]["name"]}!',
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error notifying inviter: {str(e)}")
    
    async def notify_inviter_rejected(self, rejection_data):
        """Notify inviter that their invitation was rejected"""
        try:
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                f"user_{rejection_data['inviter_id']}_invitations",
                {
                    'type': 'invitation_rejected',
                    'invitation': {
                        'id': rejection_data['invitation_id'],
                        'person_id': rejection_data['person_id'],
                        'person_name': rejection_data['person_name']
                    },
                    'message': f'{self.get_user_display_name(self.user)} declined your invitation',
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error notifying inviter of rejection: {str(e)}")
    
    async def send_error(self, message):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))
    
    @database_sync_to_async
    def get_pending_invitations(self):
        """Get all pending invitations for the current user"""
        try:
            pending = Invitation.objects.filter(
                invited_user=self.user,
                status='pending'
            ).select_related(
                'person', 
                'invited_by', 
                'invited_by__profile',
                'original_relation'
            ).order_by('-created_at')
            
            invitations = []
            for inv in pending:
                if inv.is_expired():
                    inv.status = 'expired'
                    inv.save()
                    continue
                    
                invitations.append(self.serialize_invitation(inv))
            
            return invitations
            
        except Exception as e:
            logger.error(f"Error getting pending invitations: {str(e)}", exc_info=True)
            return []
    
    @database_sync_to_async
    def get_invitation_details(self, invitation_id, token):
        """Get details for a specific invitation"""
        try:
            if token:
                invitation = Invitation.objects.get(
                    token=token,
                    invited_user=self.user
                )
            else:
                invitation = Invitation.objects.get(
                    id=invitation_id,
                    invited_user=self.user
                )
            
            if invitation.is_expired():
                return None
                
            return self.serialize_invitation(invitation)
            
        except Invitation.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting invitation details: {str(e)}", exc_info=True)
            return None
    
    @database_sync_to_async
    def process_invitation_response(self, invitation_id, token, response):
        """Process invitation response with full acceptance logic"""
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Get the invitation
                if token:
                    invitation = Invitation.objects.select_for_update().get(
                        token=token,
                        invited_user=self.user,
                        status='pending'
                    )
                else:
                    invitation = Invitation.objects.select_for_update().get(
                        id=invitation_id,
                        invited_user=self.user,
                        status='pending'
                    )
                
                # Check if expired
                if invitation.is_expired():
                    invitation.status = 'expired'
                    invitation.save()
                    return {
                        'success': False,
                        'message': 'Invitation has expired'
                    }
                
                if response == 'accept':
                    # Get or create user's person
                    user_person = Person.objects.filter(linked_user=self.user).first()
                    placeholder = invitation.person
                    inviter_person = Person.objects.filter(
                        linked_user=invitation.invited_by
                    ).first()
                    
                    # Process acceptance (your existing logic)
                    if user_person:
                        # Transfer all relations from user_person to placeholder
                        user_person.outgoing_relations.all().update(from_person=placeholder)
                        user_person.incoming_relations.all().update(to_person=placeholder)
                        
                        # Delete old person
                        old_id = user_person.id
                        user_person.delete()
                        
                        logger.info(f"Deleted old person {old_id} for user {self.user.id}")
                    
                    # Link user to placeholder
                    placeholder.linked_user = self.user
                    placeholder.is_placeholder = False
                    
                    # Update name if needed
                    display_name = self.get_user_display_name(self.user)
                    if placeholder.full_name != display_name:
                        placeholder.original_name = placeholder.full_name
                        placeholder.full_name = display_name
                    
                    placeholder.save()
                    
                    # Confirm all pending relations for this person
                    PersonRelation.objects.filter(
                        Q(from_person=placeholder) | Q(to_person=placeholder),
                        status='pending'
                    ).update(status='confirmed')
                    
                    # Create direct connection to inviter if needed
                    connection_created = False
                    if inviter_person:
                        existing = PersonRelation.objects.filter(
                            Q(from_person=placeholder, to_person=inviter_person) |
                            Q(from_person=inviter_person, to_person=placeholder)
                        ).first()
                        
                        if not existing and invitation.original_relation:
                            PersonRelation.objects.create(
                                from_person=placeholder,
                                to_person=inviter_person,
                                relation=invitation.original_relation,
                                status='confirmed',
                                created_by=self.user
                            )
                            connection_created = True
                    
                    # Update invitation
                    invitation.status = 'accepted'
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                    
                    return {
                        'success': True,
                        'invitation_id': invitation.id,
                        'person': {
                            'id': placeholder.id,
                            'name': placeholder.full_name,
                            'gender': placeholder.gender,
                            'original_name': placeholder.original_name
                        },
                        'inviter_id': invitation.invited_by.id if invitation.invited_by else None,
                        'connection_created': connection_created,
                        'message': f'Successfully connected as {placeholder.full_name}'
                    }
                    
                elif response == 'reject':
                    invitation.status = 'rejected'
                    invitation.resolved_at = timezone.now()
                    invitation.save()
                    
                    return {
                        'success': True,
                        'invitation_id': invitation.id,
                        'inviter_id': invitation.invited_by.id if invitation.invited_by else None,
                        'person_id': invitation.person.id,
                        'person_name': invitation.person.full_name,
                        'message': 'Invitation rejected'
                    }
                    
                else:  # later
                    return {
                        'success': True,
                        'invitation_id': invitation.id,
                        'message': 'Invitation kept for later'
                    }
                    
        except Invitation.DoesNotExist:
            return {
                'success': False,
                'message': 'Invitation not found'
            }
        except Exception as e:
            logger.error(f"Error in process_invitation_response: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    @database_sync_to_async
    def mark_invitations_seen(self, invitation_ids):
        """Mark invitations as seen"""
        try:
            Invitation.objects.filter(
                id__in=invitation_ids,
                invited_user=self.user
            ).update(seen_at=timezone.now())
        except Exception as e:
            logger.error(f"Error marking invitations as seen: {str(e)}")
    
    def serialize_invitation(self, invitation):
        """Serialize invitation for WebSocket transmission"""
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
                'mobile_number': invitation.invited_by.mobile_number,
                'username': invitation.invited_by.username
            },
            'original_relation': invitation.original_relation.relation_code if invitation.original_relation else None,
            'placeholder_gender': invitation.placeholder_gender,
            'created_at': invitation.created_at.isoformat() if invitation.created_at else None,
            'expires_at': invitation.expires_at.isoformat() if invitation.expires_at else None,
            'status': invitation.status,
            'is_expired': invitation.is_expired()
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