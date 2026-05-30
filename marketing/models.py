from django.db import models


class MarketingGallery(models.Model):
    image = models.ImageField(upload_to="gallery/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Gallery image #{self.id}"


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
