from ninja_keys.auth import BaseApiKeyAuth
from ..models import UserAPIKey

class UserAPIKeyAuth(BaseApiKeyAuth):
    model = UserAPIKey
    
    def authenticate(self, request, key):
        if not key:
            return None
        
        api_key = self.model.objects.get_from_key(key)
        
        if api_key is None:
            return None
        
        user = api_key.user
        if user is None or not user.is_active:
            return None
        
        return user
