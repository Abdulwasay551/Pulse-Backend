from rest_framework import serializers

from .models import (
    BackgroundCheck,
    Candidate,
    Client,
    Offboarding,
    OffboardingTask,
    OfferLetter,
    Onboarding,
    OnboardingTask,
    Requisition,
)


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
            'requirements', 'posted_at', 'candidates_count', 'created_at', 'updated_at',
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
    requisition_title = serializers.CharField(source='requisition.title', read_only=True, default=None)

    class Meta:
        model = Candidate
        fields = [
            'id', 'name', 'initials', 'role', 'email', 'phone', 'client', 'client_name',
            'requisition', 'requisition_title', 'stage', 'source', 'applied_at', 'placed_at',
            'resume_file', 'resume_text', 'ai_score', 'ai_score_notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            # applied_at is writable (defaults to today when omitted) — both
            # regular entry and CSV import need to be able to log a
            # candidate's real historical application date, not just "now".
            'id', 'placed_at', 'ai_score', 'ai_score_notes', 'created_at', 'updated_at',
        ]

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


class CandidateLiteSerializer(serializers.ModelSerializer):
    """A trimmed view of Candidate for nesting inside other serializers
    (offer letters, background checks, onboarding/offboarding) — avoids
    re-serializing the resume text/file on every one of those list views."""

    initials = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ['id', 'name', 'initials', 'role']

    def get_initials(self, obj):
        return initials_for(obj.name)


class OfferLetterSerializer(serializers.ModelSerializer):
    candidate_detail = CandidateLiteSerializer(source='candidate', read_only=True)

    class Meta:
        model = OfferLetter
        fields = [
            'id', 'candidate', 'candidate_detail', 'job_title', 'salary', 'start_date',
            'body', 'status', 'sent_at', 'signed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'sent_at', 'signed_at', 'created_at', 'updated_at']

    def validate_candidate(self, candidate):
        if candidate.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That candidate doesn't belong to you.")
        return candidate


class BackgroundCheckSerializer(serializers.ModelSerializer):
    candidate_detail = CandidateLiteSerializer(source='candidate', read_only=True)

    class Meta:
        model = BackgroundCheck
        fields = [
            'id', 'candidate', 'candidate_detail', 'check_type', 'status',
            'initiated_at', 'completed_at', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_candidate(self, candidate):
        if candidate.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That candidate doesn't belong to you.")
        return candidate


class OnboardingTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingTask
        fields = ['id', 'onboarding', 'category', 'title', 'status', 'due_date', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_onboarding(self, onboarding):
        if onboarding.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That onboarding record doesn't belong to you.")
        return onboarding


class OnboardingSerializer(serializers.ModelSerializer):
    candidate_detail = CandidateLiteSerializer(source='candidate', read_only=True)
    tasks = OnboardingTaskSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Onboarding
        fields = [
            'id', 'candidate', 'candidate_detail', 'start_date', 'status', 'tasks',
            'progress', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_progress(self, obj):
        total = obj.tasks.count()
        if not total:
            return 0
        done = obj.tasks.filter(status='Done').count()
        return round(done / total * 100)

    def validate_candidate(self, candidate):
        if candidate.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That candidate doesn't belong to you.")
        return candidate


class OffboardingTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = OffboardingTask
        fields = ['id', 'offboarding', 'category', 'title', 'status', 'due_date', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_offboarding(self, offboarding):
        if offboarding.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That offboarding record doesn't belong to you.")
        return offboarding


class OffboardingSerializer(serializers.ModelSerializer):
    candidate_detail = CandidateLiteSerializer(source='candidate', read_only=True)
    tasks = OffboardingTaskSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Offboarding
        fields = [
            'id', 'candidate', 'candidate_detail', 'last_working_day', 'reason', 'rehire_eligible',
            'status', 'tasks', 'progress', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_progress(self, obj):
        total = obj.tasks.count()
        if not total:
            return 0
        done = obj.tasks.filter(status='Done').count()
        return round(done / total * 100)

    def validate_candidate(self, candidate):
        if candidate.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That candidate doesn't belong to you.")
        return candidate
