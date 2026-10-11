"""Organization (tenant) resolution shared by every business endpoint.

There is no login system: the caller names its organization with the
``X-Organization`` header. ``OrganizationRequired`` is the default DRF
permission class, so a view is tenant-scoped unless it explicitly opts out.
The resolved organization is attached as ``request.organization``; views must
scope every query with it and never read an organization from the body.
"""

from rest_framework.permissions import BasePermission

from .exceptions import MissingOrganizationHeader, UnknownOrganization
from .models import Organization

ORGANIZATION_HEADER = "X-Organization"


def resolve_organization(request) -> Organization:
    slug = (request.headers.get(ORGANIZATION_HEADER) or "").strip().lower()
    if not slug:
        raise MissingOrganizationHeader()
    organization = Organization.objects.filter(slug=slug).first()
    if organization is None:
        raise UnknownOrganization(slug)
    return organization


class OrganizationRequired(BasePermission):
    def has_permission(self, request, view):
        request.organization = resolve_organization(request)
        return True
