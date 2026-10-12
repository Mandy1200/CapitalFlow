from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/api/", permanent=False)),
    path("api/", include("reconciliation.urls")),
]

handler404 = "reconciliation.exceptions.json_not_found"
handler500 = "reconciliation.exceptions.json_server_error"
