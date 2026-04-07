from django.urls import path
from . import views
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
from .adminviews import *


urlpatterns = [
    # Room management (REST)
    path("rooms/", views.RoomListView.as_view(), name="chat-room-list"),
    path("rooms/direct/", views.CreateDirectRoomView.as_view(), name="chat-room-direct"),
    path("rooms/group/", views.CreateGroupRoomView.as_view(), name="chat-room-group"),

    # Messages (REST — for history/pagination)
    path("rooms/<int:room_id>/messages/", views.MessageView.as_view(), name="chat-messages"),
    path("rooms/<int:room_id>/read/", views.MarkRoomReadView.as_view(), name="chat-mark-read"),
    
    # block-unblock
    path('block/',                      views.BlockUserView.as_view(),       name='block-user'),
    path('unblock/',                    views.UnblockUserView.as_view(),     name='unblock-user'),
    path('blocked/',                    views.BlockedUserListView.as_view(), name='blocked-list'),
    path('block-status/<int:user_id>/', views.BlockStatusView.as_view(),    name='block-status'),
    
    # editmessage
    path('messages/<int:message_id>/', views.UpdateMessageView.as_view(), name='edit-message'),
    
    # delete message
    path('messages/<int:message_id>/delete/', views.DeleteMessageView.as_view(),  name='chat-delete-message'),
    
    # nickname
    path('contacts/',                       views.ContactNicknameView.as_view(),   name='chat-contacts'),
    path('contacts/<int:contact_id>/',      views.ContactNicknameView.as_view(),   name='chat-contact-delete'),
    
    
    
    # clearchat
    path('rooms/<int:room_id>/delete/',      views.ClearChatView.as_view(),         name='chat-clear'),
    
    # add,remove edit
    path("rooms/<int:room_id>/members/add", views.AddGroupMembersView.as_view()),
    path("rooms/<int:room_id>/remove-members/", views.RemoveGroupMembersView.as_view()),
    path("rooms/<int:room_id>/exit/", views.LeaveGroupView.as_view()),
    
    
    # view all members in a group
    path('rooms/<int:room_id>/members/', views.GroupMembersView.as_view(), name='group-members'),
    
    
    # file upload
    path('rooms/<int:room_id>/messages/', views.MessageView.as_view(), name='create-message'),
    path('attachments/<int:attachment_id>/download/', views.DownloadAttachmentView.as_view(), name='download-attachment'),
    
    # admin
    path('admin/rooms/', AdminRoomListView.as_view(), name='admin-rooms'),
    path('admin/messages/<int:message_id>/delete/', AdminDeleteMessageView.as_view(), name='admin-delete-message'),
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('admin/groups/<int:room_id>/remove/<int:user_id>/', AdminRemoveFromGroupView.as_view(), name='admin-remove-from-group'),
    path('admin/blocked/', AdminBlockedList.as_view(), name='admin-blocked-list'),
    
    
]