from django.db import models

class DataPlan(models.Model):
    NETWORK_CHOICES = [
        ('MTN', 'MTN'),
        ('AIRTEL', 'Airtel'),
        ('GLO', 'Glo'),
        ('9MOBILE', '9mobile'),
    ]
    
    network = models.CharField(max_length=10, choices=NETWORK_CHOICES)
    plan_name = models.CharField(max_length=100) # e.g., 1GB SME (30 Days)
    plan_id = models.IntegerField(unique=True)   # The ID from CheapDataHub
    our_price = models.DecimalField(max_digits=10, decimal_places=2) # Your selling price
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.network} - {self.plan_name}"
