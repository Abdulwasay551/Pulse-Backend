from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import DemoRequestSerializer


class DemoRequestCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        demo_request = serializer.save()

        if settings.DEMO_REQUEST_NOTIFY_EMAIL:
            send_mail(
                subject=f'New demo request: {demo_request.business_name}',
                message=(
                    f'Name: {demo_request.full_name}\n'
                    f'Email: {demo_request.email}\n'
                    f'Phone: {demo_request.contact_number}\n'
                    f'Business: {demo_request.business_name}\n\n'
                    f'Message:\n{demo_request.message or "(none)"}'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEMO_REQUEST_NOTIFY_EMAIL],
                fail_silently=True,
            )

        return Response({'detail': 'Thanks — we’ll be in touch shortly.'}, status=status.HTTP_201_CREATED)
