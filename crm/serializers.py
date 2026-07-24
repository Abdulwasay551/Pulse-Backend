from rest_framework import serializers

from .models import ActivityLog, Candidate, Client, PayrollRun, Requisition


def initials_for(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper()


class ClientSerializer(serializers.ModelSerializer):
    open_roles = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'name', 'industry', 'contact_name', 'contact_email', 'status',
            'open_roles', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_open_roles(self, obj):
        return obj.requisitions.filter(status__in=Requisition.OPEN_STATUSES).count()


class RequisitionSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    candidates_count = serializers.SerializerMethodField()

    class Meta:
        model = Requisition
        fields = [
            'id', 'client', 'client_name', 'title', 'recruiter', 'priority', 'status',
            'posted_at', 'candidates_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'posted_at', 'created_at', 'updated_at']

    def get_candidates_count(self, obj):
        return obj.candidates.count()

    def validate_client(self, client):
        request = self.context['request']
        if client.owner_id != request.user.id:
            raise serializers.ValidationError("That client doesn't belong to you.")
        return client


class CandidateSerializer(serializers.ModelSerializer):
    initials = serializers.SerializerMethodField()
    client_name = serializers.CharField(source='client.name', read_only=True, default=None)

    class Meta:
        model = Candidate
        fields = [
            'id', 'name', 'initials', 'role', 'client', 'client_name', 'requisition',
            'stage', 'source', 'applied_at', 'placed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'applied_at', 'placed_at', 'created_at', 'updated_at']

    def get_initials(self, obj):
        return initials_for(obj.name)

    def _validate_owned(self, value, label):
        if value is not None and value.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError(f"That {label} doesn't belong to you.")
        return value

    def validate_client(self, client):
        return self._validate_owned(client, 'client')

    def validate_requisition(self, requisition):
        return self._validate_owned(requisition, 'requisition')


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = ['id', 'period', 'contractors', 'amount', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ['id', 'message', 'tone', 'created_at']
        read_only_fields = fields
