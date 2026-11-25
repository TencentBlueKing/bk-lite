from celery import shared_task
from django.utils import timezone

from apps.opspilot.models import SkillHistoryAnalysis
from apps.opspilot.services.history_analysis import AnalysisFailure, analyze_turns, link_findings, read_snapshot


@shared_task(name="apps.opspilot.tasks.run_history_analysis", queue="opspilot_maintenance", soft_time_limit=180, time_limit=195)
def run_history_analysis(task_id, attempt):
    jobs = SkillHistoryAnalysis.objects.filter(pk=task_id, attempt=attempt)
    if not jobs.filter(status="queued").update(status="running", updated_at=timezone.now()):
        return
    running = jobs.filter(status="running")
    try:
        task = running.select_related("skill__llm_model__vendor").get()
        turns, evidence = read_snapshot(task.skill_id, task.snapshot)
        findings = link_findings(analyze_turns(task, turns), evidence)
    except AnalysisFailure as exc:
        running.update(status="failed", failure=str(exc), updated_at=timezone.now())
    except Exception:
        # Provider exceptions may include request bodies, conversation content or credentials.
        running.update(status="failed", failure="analysis_failed", updated_at=timezone.now())
    else:
        running.update(status="completed", findings=findings, updated_at=timezone.now())


def dispatch_analysis(task_id, attempt):
    try:
        run_history_analysis.delay(task_id, attempt)
    except Exception:
        SkillHistoryAnalysis.objects.filter(pk=task_id, attempt=attempt, status="queued").update(
            status="failed", failure="dispatch_failed", updated_at=timezone.now()
        )
