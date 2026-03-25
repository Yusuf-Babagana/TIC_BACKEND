from django.db import models
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2) # Professional financial precision
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class UserMeasurement(models.Model):
    # Linked to user for FR-18: Input body measurements
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    neck = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chest = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    waist = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    shoulder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

class CustomStyleRequest(models.Model):
    # For FR-17 and FR-19: Custom sewing and reference images
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),    # User just submitted
        ('quoted', 'Price Quoted'),       # Admin set a price
        ('paid', 'Payment Confirmed'),    # User paid from wallet
        ('cutting', 'Cutting Fabric'),    # Production started
        ('sewing', 'Sewing in Progress'), # Tailor is working
        ('completed', 'Ready/Shipped'),   # Done
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    description = models.TextField()
    reference_image = models.ImageField(upload_to='custom_requests/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    price_quote = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
