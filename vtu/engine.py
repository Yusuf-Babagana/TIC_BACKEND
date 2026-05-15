import requests
from django.conf import settings
from .providers import PROVIDERS

class VTUEngine:
    BASE_URL = "https://www.cheapdatahub.ng/api/v1/resellers"
    HEADERS = {
        "Authorization": f"Bearer {settings.CHEAPDATAHUB_API_KEY}",
        "Content-Type": "application/json"
    }

    @classmethod
    def purchase(cls, user, service_type, payload):
        """
        service_type: 'airtime', 'data', 'electricity', 'cable'
        """
        # 1. Validation & Local Wallet Check
        amount_to_deduct = payload.get('amount')
        if user.wallet.balance < amount_to_deduct:
            return {"status": "false", "message": "Insufficient TIC Wallet Balance"}

        # 2. Endpoint Mapping
        endpoints = {
            "airtime": "/airtime/purchase/",
            "data": "/data/purchase/",
            "electricity": "/electricity/purchase/",
            "cable": "/cable/purchase/"
        }

        url = f"{cls.BASE_URL}{endpoints[service_type]}"
        
        # 3. Call CheapDataHub
        response = requests.post(url, json=payload, headers=cls.HEADERS)
        result = response.json()

        # 4. Success Handling
        if result.get('status') == "true":
            user.wallet.balance -= amount_to_deduct
            user.wallet.save()
            # Log the successful transaction in TIC DB
            
        return result
