from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from wallet.models import Wallet
from wallet.monnify import MonnifyService

User = get_user_model()

@receiver(post_save, sender=User)
def handle_user_onboarding(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Local Wallet first
        wallet = Wallet.objects.create(user=instance)
        
        # 2. Call Monnify to generate the Reserved Account
        try:
            response = MonnifyService.create_reserved_account(instance)
            
            if response.get('requestSuccessful'):
                # Extract details from Monnify v2 responseBody
                accounts = response['responseBody']['accounts']
                if accounts:
                    # We take the first bank account provided (usually Wema or Sterling)
                    wallet.bank_name = accounts[0]['bankName']
                    wallet.account_number = accounts[0]['accountNumber']
                    wallet.account_reference = response['responseBody']['accountReference']
                    wallet.save()
        except Exception as e:
            # Log the error so you can retry manually if the API was down
            print(f"Monnify Error for {instance.username}: {str(e)}")
