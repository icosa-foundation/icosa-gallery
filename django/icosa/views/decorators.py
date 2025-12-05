from functools import wraps

from django.core.cache import cache as core_cache


def cache_key(request):
    user_id = "anonymous" if request.user.is_anonymous else request.user.id

    q = getattr(request, request.method)
    # q.lists()
    urlencode = q.urlencode(safe="()")

    CACHE_KEY = f"view_cache_{request.path}_{user_id}_{urlencode}"
    return CACHE_KEY


def cache_per_user(ttl=None, prefix=None):
    def decorator(view_function):
        @wraps(view_function)
        def apply_cache(request, *args, **kwargs):
            CACHE_KEY = cache_key(request)

            if prefix:
                CACHE_KEY = f"{prefix}_{CACHE_KEY}"

            can_cache = request.method in ["GET", "HEAD", "OPTIONS"]

            if can_cache:
                response = core_cache.get(CACHE_KEY, None)
            else:
                response = None

            if not response:
                response = view_function(request, *args, **kwargs)
                if can_cache:
                    core_cache.set(CACHE_KEY, response, ttl)
            return response

        return apply_cache

    return decorator
