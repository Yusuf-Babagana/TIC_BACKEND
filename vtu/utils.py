import requests
from django.conf import settings

class CheapDataHubService:
    def __init__(self):
        self.api_key = settings.CHEAPDATAHUB_API_KEY
        self.base_url = "https://www.cheapdatahub.ng/api/v1/resellers/"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def get_balance(self):
        response = requests.get(f"{self.base_url}wallet/balance/", headers=self.headers)
        return response.json()

    def purchase_airtime(self, provider_id, phone, amount):
        payload = {
            "provider_id": provider_id,
            "phone_number": phone,
            "amount": amount
        }
        response = requests.post(f"{self.base_url}airtime/purchase/", json=payload, headers=self.headers)
        return response.json()

    def purchase_data(self, bundle_id, phone):
        payload = {
            "bundle_id": bundle_id,
            "phone_number": phone
        }
        response = requests.post(f"{self.base_url}data/purchase/", json=payload, headers=self.headers)
        return response.json()
