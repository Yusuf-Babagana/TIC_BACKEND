from rest_framework import generics
from rest_framework.views import APIView
from .models import DataPlan
from .serializers import DataPlanSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .services import CheapDataHubService
from wallet.models import Wallet # Assuming you have a wallet app

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
            # Transaction.objects.create(user=request.user, amount=amount, type='Airtime')

        return Response(vtu_response)

class DataPlanListView(generics.ListAPIView):
    serializer_class = DataPlanSerializer

    def get_queryset(self):
        network = self.request.query_params.get('network')
        if network:
            return DataPlan.objects.filter(network=network, is_active=True)
        return DataPlan.objects.filter(is_active=True)
