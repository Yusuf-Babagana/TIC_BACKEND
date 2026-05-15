from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .serializers import TransactionSerializer
from rest_framework.response import Response
from .models import Wallet, Transaction

class MonnifyWebhookView(APIView):
    permission_classes = [] # Public because Monnify calls it

    def post(self, request):
        data = request.data
        # 1. Verify hash/signature here for security!
        
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
        # Only show transactions belonging to the logged-in user
        return Transaction.objects.filter(user=self.request.user).order_by('-created_at')
