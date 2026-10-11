import logging

from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class MissingOrganizationHeader(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "missing_organization"
    default_detail = "The X-Organization header is required."


class UnknownOrganization(exceptions.APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "unknown_organization"

    def __init__(self, slug: str):
        super().__init__(f"Organization '{slug}' was not found.")


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "The request conflicts with the current state of the resource."

    def __init__(self, message: str, code: str = "conflict"):
        super().__init__(message, code)


def error_body(code: str, message: str, details=None) -> dict:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def api_exception_handler(exc, context):
    # Imported here: rest_framework.views imports the permission classes, which import this module.
    from rest_framework.views import exception_handler

    if isinstance(exc, Http404):
        exc = exceptions.NotFound(str(exc) or "Not found.")
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            error_body("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        details = exc.detail
        message = _first_message(details) or "Invalid request."
        response.data = error_body("invalid", message, details)
    elif isinstance(exc, exceptions.APIException):
        detail = exc.detail
        code = detail.code if hasattr(detail, "code") else exc.default_code
        response.data = error_body(str(code), str(detail))
    return response


def _first_message(details):
    if isinstance(details, list) and details:
        return _first_message(details[0])
    if isinstance(details, dict) and details:
        return _first_message(next(iter(details.values())))
    if details:
        return str(details)
    return None


def json_not_found(request, exception=None):
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def json_server_error(request):
    return JsonResponse(error_body("server_error", "An unexpected error occurred."), status=500)
