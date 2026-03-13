from django_filters import rest_framework as filters
from .models import Event

class EventFilter(filters.FilterSet):
    """
    Filter events based on user profile and visibility
    """
    start_date_after = filters.DateFilter(field_name='start_date', lookup_expr='gte')
    start_date_before = filters.DateFilter(field_name='start_date', lookup_expr='lte')
    event_type = filters.CharFilter(field_name='event_type__code')
    city = filters.CharFilter(lookup_expr='icontains')
    
    # Visibility filters (admin only)
    status = filters.CharFilter()
    created_by = filters.NumberFilter()
    
    class Meta:
        model = Event
        fields = ['event_type', 'city', 'state', 'country', 'is_virtual', 'status']
    
    def filter_queryset(self, queryset):
        """
        Automatically filter based on requesting user
        """
        request = self.request
        queryset = super().filter_queryset(queryset)
        
        # Admin sees all
        if request.user.is_staff:
            return queryset
        
        # Filter based on visibility
        visible_events = []
        for event in queryset:
            if event.is_visible_to(request.user):
                visible_events.append(event.id)
        
        return queryset.filter(id__in=visible_events)