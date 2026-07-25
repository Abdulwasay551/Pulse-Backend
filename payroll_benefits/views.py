from core.activity import log_activity
from core.permissions import IsOwner
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import PayrollRun
from .serializers import PayrollRunSerializer


class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        run = serializer.save(owner=self.request.user)
        if run.status == 'Needs review':
            log_activity(self.request.user, f'{run.period} payroll needs review', 'amber')
        else:
            log_activity(self.request.user, f'{run.period} payroll processed', 'primary')
