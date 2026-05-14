import requests
from django.conf import settings

class CheapDataHubService:
    BASE_URL = "https://www.cheapdatahub.ng/api/v1/resellers"
    HEADERS = {
        "Authorization": f"Bearer {settings.CHEAPDATAHUB_API_KEY}",
        "Content-Type": "application/json"
    }

    @staticmethod
    def get_balance():
        url = f"{CheapDataHubService.BASE_URL}/wallet/balance/"
        response = requests.get(url, headers=CheapDataHubService.HEADERS)
        return response.json()

    @staticmethod
    def purchase_airtime(provider_id, phone_number, amount):
        url = f"{CheapDataHubService.BASE_URL}/airtime/purchase/"
        payload = {
            "provider_id": provider_id,
            "phone_number": phone_number,
            "amount": amount
        }
        response = requests.post(url, json=payload, headers=CheapDataHubService.HEADERS)
        return response.json()

    @staticmethod
    def purchase_data(bundle_id, phone_number):
        url = f"{CheapDataHubService.BASE_URL}/data/purchase/"
        payload = {
            "bundle_id": bundle_id,
            "phone_number": phone_number
        }
        response = requests.post(url, json=payload, headers=CheapDataHubService.HEADERS)
        return response.json()
