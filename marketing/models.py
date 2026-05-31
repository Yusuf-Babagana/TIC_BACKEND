from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total(self):
        return sum(ci.total() for ci in self.items.all())

    def __str__(self):
        return f"Cart #{self.id} ({self.user.username})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    gallery_item = models.ForeignKey("MarketingGallery", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def total(self):
        return self.gallery_item.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.gallery_item.title}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sewing", "Sewing"),
        ("ready", "Ready"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gallery_orders")
    reference = models.CharField(max_length=100, unique=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    delivery_address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} ({self.reference})"


class MarketingGallery(models.Model):
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="gallery/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    gallery_item = models.ForeignKey(MarketingGallery, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    image_url = models.URLField(blank=True)

    def total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.title}"


class Flyer(models.Model):
    POSITION_CHOICES = [(1, "Flyer 1"), (2, "Flyer 2")]

    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to="flyers/")
    link_url = models.URLField(max_length=500, blank=True)
    position = models.IntegerField(choices=POSITION_CHOICES, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"{self.title} (Flyer {self.position})"
