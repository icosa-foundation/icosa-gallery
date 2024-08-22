from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.urls import is_valid_path
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import escape_leading_slashes


class RemoveSlashMiddleware(MiddlewareMixin):
    """
    This middleware removes a given trailing slash if the resulting path is
    valid. It doesn't change admin-URLs.
    """

    response_redirect_class = HttpResponsePermanentRedirect

    def get_full_path_without_slash(self, request):
        """
        Return the full path of the request with a trailing slash appended.

        Raise a RuntimeError if settings.DEBUG is True and request.method is
        POST, PUT, or PATCH.
        """
        new_path = request.get_full_path(force_append_slash=False).rstrip("/")
        # Prevent construction of scheme relative urls.
        new_path = escape_leading_slashes(new_path)
        if settings.DEBUG and request.method in ("POST", "PUT", "PATCH"):
            raise RuntimeError(
                "You called this URL via %(method)s, but the URL ends "
                "in a slash and you have APPEND_SLASH set. Django can't "
                "redirect to the non-slash URL while maintaining %(method)s data. "
                "Change your form to point to %(url)s (note the lack of trailing "
                "slash), or set APPEND_SLASH=True in your Django settings."
                % {
                    "method": request.method,
                    "url": request.get_host() + new_path,
                }
            )
        return new_path

    def should_redirect_without_slash(self, request):
        """
        Return True if settings.APPEND_SLASH is True and appending a slash to
        the request path turns an invalid path into a valid one.
        """
        if (
            not settings.APPEND_SLASH
            and request.path_info.endswith("/")
            and not request.path_info.startswith("/admin")
        ):
            urlconf = settings.ROOT_URLCONF
            if not is_valid_path(request.path_info, urlconf):
                new_path = request.path_info.rstrip("/")
                match = is_valid_path(new_path, urlconf)
                if match:
                    return True
        return False

    def process_response(self, request, response):
        """
        When the status code of the response is 404, it may redirect to a path
        with an appended slash if should_redirect_with_slash() returns True.
        """
        # If the given URL is "Not Found", then check if we should redirect to
        # a path with the slash removed.
        if response.status_code == 404 and self.should_redirect_without_slash(
            request
        ):
            return self.response_redirect_class(
                self.get_full_path_without_slash(request)
            )

        # Add the Content-Length header to non-streaming responses if not
        # already set.
        if not response.streaming and not response.has_header(
            "Content-Length"
        ):
            response.headers["Content-Length"] = str(len(response.content))

        return response
