from rest_framework import serializers
from .models import Transaction, Wallet


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ["balance", "bank_name", "account_number", "account_reference", "account_name"]


class TransactionSerializer(serializers.ModelSerializer):
    formatted_date = serializers.DateTimeField(
        source="created_at", format="%d %b, %Y - %I:%M %p", read_only=True
    )

    class Meta:
        model = Transaction
        fields = ["id", "trans_type", "amount", "reference", "order_id", "status", "formatted_date"]
