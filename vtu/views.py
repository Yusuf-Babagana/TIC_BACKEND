import requests
from django.conf import settings
from rest_framework.views import APIView
from .models import DataPlan
from .serializers import DataPlanSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .services import CheapDataHubService
from wallet.models import Transaction


class AirtimePurchaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        phone = request.data.get('phone_number')
        provider = request.data.get('provider_id')

        # 1. Check local TIC Wallet balance first
        user_wallet = request.user.wallet
        if user_wallet.balance < amount:
            return Response({"status": "false", "message": "Insufficient TIC Wallet balance"}, status=402)

        # 2. Call CheapDataHub
        vtu_response = CheapDataHubService.purchase_airtime(provider, phone, amount)

        if vtu_response.get('status') == "true":
            # 3. Deduct from TIC Wallet only if successful
            user_wallet.balance -= amount
            user_wallet.save()

            # 4. Log the transaction locally for the user
            Transaction.objects.create(
                user=request.user,
                trans_type='AIRTIME',
                amount=amount,
                reference=vtu_response.get('reference', 'N/A'),
                status='SUCCESSFUL'
            )

        return Response(vtu_response)

class DataPlanListView(APIView):
    # This allows the phone to fetch plans without a token
    permission_classes = [AllowAny] 

    def get(self, request):
        try:
            network = request.query_params.get('network')
            if network:
                plans = DataPlan.objects.filter(network=network.upper(), is_active=True)
            else:
                plans = DataPlan.objects.filter(is_active=True)
            
            serializer = DataPlanSerializer(plans, many=True)
            return Response(serializer.data)
        except Exception as e:
            # This helps us see the error in the mobile log
            return Response({"error": str(e)}, status=500)

class VTUPurchaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data
        
        # 1. Extract parameters
        # service_type can be 'airtime', 'data', 'electricity', or 'cable'
        service_type = data.get('service_type')
        amount = float(data.get('amount', 0))
        
        # 2. Local Wallet Check
        if user.wallet.balance < amount:
            return Response({"status": "false", "message": "Insufficient TIC Wallet balance"}, status=400)

        # 3. Construct CheapDataHub Request
        url_map = {
            "airtime": "airtime/purchase/",
            "data": "data/purchase/",
            "electricity": "electricity/purchase/",
            "cable": "cable/purchase/"
        }
        
        url = f"https://www.cheapdatahub.ng/api/v1/resellers/{url_map.get(service_type)}"
        headers = {"Authorization": f"Bearer {settings.CHEAPDATAHUB_API_KEY}"}
        
        # 4. Call Provider
        try:
            # We pass the payload directly as received from the mobile app
            response = requests.post(url, json=data, headers=headers)
            res_data = response.json()

            # 5. Handle Success
            if res_data.get('status') == "true":
                user.wallet.balance -= amount
                user.wallet.save()
                
                trans_mapping = {
                    'airtime': 'AIRTIME',
                    'data': 'DATA',
                    'electricity': 'UTILITY',
                    'cable': 'UTILITY'
                }
                # Log transaction
                Transaction.objects.create(
                    user=request.user,
                    trans_type=trans_mapping.get(service_type, 'DATA'),
                    amount=amount,
                    reference=res_data.get('reference', 'N/A'),
                    status='SUCCESSFUL'
                )
            
            return Response(res_data)
        except Exception as e:
            return Response({"status": "false", "message": "Connection to provider failed"}, status=500)
