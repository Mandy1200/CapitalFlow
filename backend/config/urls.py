from django.urls import include, path

urlpatterns = [
    path("api/", include("reconciliation.urls")),
]

handler404 = "reconciliation.exceptions.json_not_found"
handler500 = "reconciliation.exceptions.json_server_error"
