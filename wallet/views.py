import hashlib
import hmac
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .serializers import TransactionSerializer
from rest_framework.response import Response
from .models import Wallet, Transaction

class MonnifyWebhookView(APIView):
    permission_classes = []

    def _verify_signature(self, request):
        signature = request.headers.get('monnify-signature')
        if not signature:
            return False
        expected = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode('utf-8'),
            request.body,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def post(self, request):
        if not self._verify_signature(request):
            return Response({"status": "invalid signature"}, status=403)

        data = request.data
        
        if data.get('paymentStatus') == 'PAID':
            ref = data.get('paymentReference')
            amount = float(data.get('amountPaid'))
            customer_email = data['customer']['email']
            
            # Find user by email and update wallet
            try:
                wallet = Wallet.objects.get(user__email=customer_email)
                wallet.balance += amount
                wallet.save()
                
                # Log deposit transaction
                Transaction.objects.create(
                    user=wallet.user,
                    trans_type='DEPOSIT',
                    amount=amount,
                    reference=ref,
                    status='SUCCESSFUL'
                )
                return Response({"status": "success"}, status=200)
            except Wallet.DoesNotExist:
                return Response({"status": "error"}, status=404)
        
        return Response({"status": "ignored"}, status=200)

class TransactionHistoryView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by('-created_at')

class GenerateAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        wallet = request.user.wallet
        if wallet.account_number:
            return Response({"message": "Account already exists"}, status=400)
            
        # Re-run the onboarding logic
        from .monnify import MonnifyService
        try:
            response = MonnifyService.create_reserved_account(request.user)
            
            if response.get('requestSuccessful'):
                accounts = response['responseBody']['accounts']
                if accounts:
                    wallet.bank_name = accounts[0]['bankName']
                    wallet.account_number = accounts[0]['accountNumber']
                    wallet.account_reference = response['responseBody']['accountReference']
                    wallet.save()
                    return Response({"message": "Account generated successfully"})
            return Response({"message": "Failed to generate account. Please try again."}, status=400)
        except Exception as e:
            return Response({"message": str(e)}, status=500)
