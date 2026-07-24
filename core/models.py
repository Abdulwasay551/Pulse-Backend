from django.db import models


class DemoRequest(models.Model):
    """A submission of the public "Book a Demo" form."""

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    contact_number = models.CharField(max_length=30)
    business_name = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.business_name})'
