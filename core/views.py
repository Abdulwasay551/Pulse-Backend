from django.conf import settings
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


def landing(request):
    return render(request, 'core/landing.html', {'frontend_url': settings.FRONTEND_URL})
