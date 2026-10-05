from django.urls import path

from backend.api import views

urlpatterns = [
    path("health", views.HealthView.as_view()),
    # Visitor
    path("events", views.EventCollectionView.as_view()),
    path("events/<str:event_id>", views.EventDetailView.as_view()),
    path("events/<str:event_id>/registrations", views.EventRegistrationsView.as_view()),
    # Organiser
    path("organiser/events", views.OrganiserEventsView.as_view()),
    # Administrator
    path("events/<str:event_id>/publish", views.EventPublishView.as_view()),
    path("admin/events", views.AdminEventsView.as_view()),
    path("admin/activity", views.AdminActivityView.as_view()),
]
