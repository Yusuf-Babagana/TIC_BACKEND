from datetime import timedelta

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
    # Upper body (shirt, top & kaftan)
    neck = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chest = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    shoulder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sleeve_length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bicep = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    wrist = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Lower body (trousers & shorts)
    waist = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hips = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    trouser_length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    inseam = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    thigh = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    knee = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ankle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    crotch = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Caps, agbada & fitting notes
    cap_size = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    agbada_length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    last_updated = models.DateTimeField(auto_now=True)

class FabricBrand(models.Model):
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class FabricGrade(models.Model):
    brand = models.ForeignKey(FabricBrand, on_delete=models.CASCADE, related_name="grades")
    name = models.CharField(max_length=50)
    price = models.PositiveIntegerField()

    class Meta:
        ordering = ["brand__position", "price"]

    def __str__(self):
        return f"{self.brand.name} - {self.name}"


class FabricColor(models.Model):
    grade = models.ForeignKey(FabricGrade, on_delete=models.CASCADE, related_name="colors")
    name = models.CharField(max_length=50)
    swatch_image = models.ImageField(upload_to="fabric_colors/", blank=True, null=True)

    class Meta:
        ordering = ["grade", "name"]

    def __str__(self):
        return f"{self.grade} - {self.name}"


class CustomStyleRequest(models.Model):
    # For FR-17 and FR-19: Custom sewing and reference images
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),    # User just submitted
        ('quoted', 'Price Quoted'),       # Admin set a price
        ('expired', 'Quote Expired'),     # Quote not paid within the validity window
        ('paid', 'Payment Confirmed'),    # User paid from wallet
        ('cutting', 'Cutting Fabric'),    # Production started
        ('sewing', 'Sewing in Progress'), # Tailor is working
        ('completed', 'Ready for Delivery'),  # Ready to deliver
        ('delivered', 'Delivered'),       # Delivered to customer
    ]
    QUOTE_VALIDITY = timedelta(days=3)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    description = models.TextField()
    reference_image = models.ImageField(upload_to='custom_requests/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # price_quote is always fabric_fee + tailoring_fee — kept as a stored,
    # authoritative total (rather than a computed property) since it's what
    # PayForTailoringView actually charges against.
    price_quote = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fabric_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tailoring_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fabric_grade = models.ForeignKey(
        FabricGrade, on_delete=models.SET_NULL, null=True, blank=True, related_name="requests"
    )
    fabric_color = models.ForeignKey(
        FabricColor, on_delete=models.SET_NULL, null=True, blank=True, related_name="requests"
    )
    delivery_address = models.TextField(blank=True, default="")
    quote_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    order = models.ForeignKey(CustomStyleRequest, on_delete=models.CASCADE, null=True, blank=True)
    # 500, not 255 — a Broadcast-sourced notification packs an icon + title + body into this
    # field (see Broadcast.send()) and 255 was too tight for that combination.
    message = models.CharField(max_length=500)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{'Read' if self.is_read else 'Unread'}] {self.user.username}: {self.message[:50]}"


class Broadcast(models.Model):
    """
    An admin-authored announcement sent to every active user in one shot — maintenance
    notices, bonus/promo pushes, or anything else vital. Sending it (see send()) fans out
    a Notification row per user plus a push notification, so it shows up both in-app and
    even if the app isn't open. This row itself is just the send record/history.
    """
    CATEGORY_GENERAL = "general"
    CATEGORY_MAINTENANCE = "maintenance"
    CATEGORY_BONUS = "bonus"
    CATEGORY_CHOICES = [
        (CATEGORY_GENERAL, "General / Vital Info"),
        (CATEGORY_MAINTENANCE, "Maintenance Notice"),
        (CATEGORY_BONUS, "Bonus / Promotion"),
    ]
    CATEGORY_ICONS = {
        CATEGORY_GENERAL: "📢",
        CATEGORY_MAINTENANCE: "🔧",
        CATEGORY_BONUS: "🎁",
    }

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_GENERAL)
    title = models.CharField(max_length=60)
    body = models.CharField(max_length=400)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="broadcasts_sent"
    )
    recipient_count = models.PositiveIntegerField(default=0)
    push_sent_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.category}] {self.title}"

    @property
    def icon(self):
        return self.CATEGORY_ICONS.get(self.category, "📢")

    def send(self):
        """
        Fans this announcement out to every active user: one Notification row each (so it
        shows in the in-app list) plus a batched Expo push (so it shows even with the app
        closed). Best-effort on the push side — a delivery failure never blocks the in-app
        side, which is the reliable source of truth once the user opens the app.
        """
        from core.push import send_push_notifications_bulk
        from django.contrib.auth import get_user_model

        User = get_user_model()
        message = f"{self.icon} {self.title}\n{self.body}"

        recipients = list(User.objects.filter(is_active=True))
        Notification.objects.bulk_create(
            [Notification(user=user, message=message) for user in recipients]
        )

        push_messages = [
            {
                "to": user.push_token,
                "title": f"{self.icon} {self.title}",
                "body": self.body,
                "sound": "default",
                "data": {"type": "broadcast", "category": self.category},
            }
            for user in recipients
            if user.push_token
        ]
        sent = send_push_notifications_bulk(push_messages)

        self.recipient_count = len(recipients)
        self.push_sent_count = sent
        self.save(update_fields=["recipient_count", "push_sent_count"])
