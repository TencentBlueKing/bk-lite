from datetime import timedelta
from functools import partial

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.models import SkillHistoryAnalysis
from apps.opspilot.services.history_analysis import ChannelScopeInput, ScopeInput, TaskInput, available_channels, capture_scope
from apps.opspilot.services.history_analysis_pdf import render_analysis_pdf
from apps.opspilot.tasks.history_analysis import dispatch_analysis


class AnalysisSummary(serializers.ModelSerializer):
    class Meta:
        model = SkillHistoryAnalysis
        fields = ("id", "name", "objective", "scope", "creator", "created_at", "status", "failure", "conversation_count", "question_count")


def positive_id(params, field):
    return serializers.IntegerField(min_value=1, max_value=2**63 - 1).run_validation(params.get(field))


class HistoryAnalysisActions:
    def _analysis_access(self, request):
        params = request.query_params if request.method == "GET" else request.data
        return self._get_managed_skill(request, positive_id(params, "skill_id"))

    def _analysis_jobs(self, request, skill):
        jobs = SkillHistoryAnalysis.objects.filter(skill=skill, team=get_current_team(request, "0"))
        # A killed worker or lost broker delivery must become retryable.
        now = timezone.now()
        jobs.filter(status="running", updated_at__lt=now - timedelta(minutes=5)).update(status="failed", failure="expired", updated_at=now)
        jobs.filter(status="queued", updated_at__lt=now - timedelta(hours=1)).update(status="failed", failure="expired", updated_at=now)
        return jobs

    @HasPermission("skill_setting-View")
    @action(methods=["POST"], detail=False)
    def analysis_channels(self, request):
        skill = self._analysis_access(request)
        if isinstance(skill, JsonResponse):
            return skill
        scope = ChannelScopeInput(data=request.data)
        scope.is_valid(raise_exception=True)
        return Response({"items": available_channels(skill, scope.validated_data)})

    @HasPermission("skill_setting-View")
    @action(methods=["POST"], detail=False)
    def analysis_preview(self, request):
        skill = self._analysis_access(request)
        if isinstance(skill, JsonResponse):
            return skill
        scope = ScopeInput(data=request.data)
        scope.is_valid(raise_exception=True)
        summary, _ = capture_scope(skill, scope.validated_data)
        return Response(summary)

    @HasPermission("skill_setting-View")
    @action(methods=["GET", "POST"], detail=False)
    def analyses(self, request):
        skill = self._analysis_access(request)
        if isinstance(skill, JsonResponse):
            return skill
        jobs = self._analysis_jobs(request, skill)
        if request.method == "GET":
            page = serializers.IntegerField(min_value=1, max_value=1000000).run_validation(request.query_params.get("page", 1))
            rows = jobs.defer("snapshot", "findings").order_by("-pk")[(page - 1) * 10 : page * 10]
            return Response({"items": AnalysisSummary(rows, many=True).data, "count": jobs.count()})

        form = TaskInput(data=request.data)
        form.is_valid(raise_exception=True)
        data = dict(form.validated_data)
        creator = f"{request.user.username}@{request.user.domain}" if request.user.domain else request.user.username
        identity = dict(skill=skill, team=get_current_team(request, "0"), creator=creator, request_id=data.pop("request_id"))
        existing = jobs.filter(creator=creator, request_id=identity["request_id"]).first()
        if existing:
            return Response(AnalysisSummary(existing).data)
        scope = ScopeInput(data=request.data)
        scope.is_valid(raise_exception=True)
        summary, snapshot = capture_scope(skill, scope.validated_data)
        if summary.pop("issue"):
            return Response({"result": False, "message": "范围为空或过大，请重新预览"}, status=400)
        report_scope = {**scope.data, "channel_types": summary.pop("channel_types")}
        locale = request.headers.get("X-BK-Locale") or getattr(request.user, "locale", "") or "cn"
        with transaction.atomic():
            task, created = SkillHistoryAnalysis.objects.get_or_create(
                **identity,
                defaults=dict(**data, **summary, scope=report_scope, snapshot=snapshot, locale="en" if locale.lower().startswith("en") else "cn"),
            )
            if created:
                transaction.on_commit(partial(dispatch_analysis, task.pk, task.attempt))
        return Response(AnalysisSummary(task).data, status=201 if created else 200)

    @HasPermission("skill_setting-View")
    @action(methods=["GET"], detail=False)
    def analysis_report(self, request):
        skill = self._analysis_access(request)
        if isinstance(skill, JsonResponse):
            return skill
        task = get_object_or_404(self._analysis_jobs(request, skill), pk=positive_id(request.query_params, "task_id"))
        if task.status != "completed":
            return Response({"result": False, "message": "报告尚未生成"}, status=409)
        if request.query_params.get("download") == "pdf":
            response = HttpResponse(render_analysis_pdf(task), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="analysis-{task.pk}.pdf"'
            response["Cache-Control"] = "private, no-store"
            return response
        return Response({**AnalysisSummary(task).data, "focus": task.focus, "findings": task.findings})

    @HasPermission("skill_setting-View")
    @action(methods=["POST"], detail=False)
    def analysis_retry(self, request):
        skill = self._analysis_access(request)
        if isinstance(skill, JsonResponse):
            return skill
        with transaction.atomic():
            task = get_object_or_404(self._analysis_jobs(request, skill).select_for_update(), pk=positive_id(request.data, "task_id"))
            if task.status != "failed":
                return Response({"result": False, "message": "仅失败的任务可重试"}, status=409)
            task.attempt += 1
            task.status = "queued"
            task.failure = ""
            task.save(update_fields=["attempt", "status", "failure", "updated_at"])
            transaction.on_commit(partial(dispatch_analysis, task.pk, task.attempt))
        return Response(AnalysisSummary(task).data)
