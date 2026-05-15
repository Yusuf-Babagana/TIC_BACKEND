from rest_framework import serializers
from .models import Transaction

class TransactionSerializer(serializers.ModelSerializer):
    # Format date like "15 May, 2026 - 05:20 PM"
    formatted_date = serializers.DateTimeField(source='created_at', format="%d %b, %Y - %I:%M %p", read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['id', 'trans_type', 'amount', 'reference', 'status', 'formatted_date']
