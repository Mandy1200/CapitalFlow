from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("organizations/", views.OrganizationListView.as_view(), name="organizations"),
    path("imports/", views.ImportView.as_view(), name="imports"),
    path("transactions/", views.TransactionListView.as_view(), name="transactions"),
    path("transactions/<int:pk>/", views.TransactionDetailView.as_view(), name="transaction-detail"),
    path("transactions/<int:pk>/ignore/", views.TransactionIgnoreView.as_view(), name="transaction-ignore"),
    path("line-items/", views.LineItemListView.as_view(), name="line-items"),
    path("matches/<int:pk>/approve/", views.MatchActionView.as_view(match_action="approve"), name="match-approve"),
    path("matches/<int:pk>/reject/", views.MatchActionView.as_view(match_action="reject"), name="match-reject"),
]
