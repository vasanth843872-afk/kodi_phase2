from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import UserProfile
from .serializers import (
    PublicProfileSerializer,
    PrivateProfileSerializer,
    ProfileUpdateSerializer
)

class MyProfileView(generics.RetrieveUpdateAPIView):
    """View for current user's profile."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return PrivateProfileSerializer
        return ProfileUpdateSerializer
    
    def get_object(self):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile
    
    def retrieve(self, request, *args, **kwargs):
        """Return full profile for owner."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class PublicProfileView(generics.RetrieveAPIView):
    """View for public profile of other users."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PublicProfileSerializer
    queryset = UserProfile.objects.all()
    lookup_field = 'user__id'
    
    def get_object(self):
        """Get profile by user ID."""
        user_id = self.kwargs.get('user_id')
        return get_object_or_404(UserProfile, user__id=user_id)

class ProfileCompletionStatusView(APIView):
    """Check profile completion status."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Define required fields for each step
        step1_fields = [
            'firstname', 'gender', 'preferred_language'
        ]
        step2_fields = [
            'dateofbirth', 'present_city', 'state', 'nationality'
        ]
        step3_fields = [
            'familyname1', 'religion', 'caste'
        ]
        
        # Calculate completion percentages
        def calculate_completion(fields):
            total = len(fields)
            completed = sum(1 for field in fields if getattr(profile, field))
            return (completed / total * 100) if total > 0 else 0
        
        completion = {
            'step1_percentage': calculate_completion(step1_fields),
            'step2_percentage': calculate_completion(step2_fields),
            'step3_percentage': calculate_completion(step3_fields),
            'total_percentage': calculate_completion(step1_fields + step2_fields + step3_fields),
            'is_complete': all([
                calculate_completion(step1_fields) == 100,
                calculate_completion(step2_fields) == 100,
                calculate_completion(step3_fields) == 100
            ])
        }
        
        return Response(completion)