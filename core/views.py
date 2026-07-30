from django.conf import settings
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Announcement
from .permissions import IsOwner
from .serializers import AnnouncementSerializer


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


def landing(request):
    return render(request, 'core/landing.html', {'frontend_url': settings.FRONTEND_URL})


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
