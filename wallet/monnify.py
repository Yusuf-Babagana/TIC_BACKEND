import requests
import base64
from django.conf import settings

class MonnifyService:
    BASE_URL = "https://api.monnify.com/api/v1" # Auth is v1, but resources are v2
    
    @classmethod
    def _get_token(cls):
        """Authenticates with Monnify and returns access token"""
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {"Authorization": f"Basic {encoded_auth}"}
        response = requests.post(f"{cls.BASE_URL}/auth/login", headers=headers)
        return response.json()['responseBody']['accessToken']

    @classmethod
    def create_reserved_account(cls, user):
        """Creates a dedicated bank account for a user"""
        token = cls._get_token()
        url = "https://api.monnify.com/api/v2/bank-transfer/reserved-accounts"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "accountReference": f"TIC-{user.id}-{user.username}",
            "accountName": f"TIC-{user.first_name} {user.last_name}",
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": f"{user.first_name} {user.last_name}",
            "getAllAvailableBanks": True
        }
        
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
