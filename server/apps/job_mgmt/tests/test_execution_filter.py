"""作业执行过滤器单元测试（发起人 created_by / 触发来源 trigger_source）"""

import pytest

from apps.job_mgmt.constants import TriggerSource
from apps.job_mgmt.filters.execution import JobExecutionFilter
from apps.job_mgmt.models import JobExecution


@pytest.mark.unit
@pytest.mark.django_db
class TestJobExecutionFilter:
    def _make(self, **kwargs):
        defaults = {"name": "job", "job_type": "script", "status": "success"}
        defaults.update(kwargs)
        return JobExecution.objects.create(**defaults)

    def test_filter_by_created_by_icontains(self):
        """按发起人模糊过滤"""
        self._make(created_by="admin")
        self._make(created_by="alice")

        qs = JobExecutionFilter({"created_by": "adm"}, queryset=JobExecution.objects.all()).qs

        assert [e.created_by for e in qs] == ["admin"]

    def test_filter_by_trigger_source_single(self):
        """按单个触发来源过滤"""
        self._make(trigger_source=TriggerSource.MANUAL)
        self._make(trigger_source=TriggerSource.SCHEDULED)

        qs = JobExecutionFilter({"trigger_source": "manual"}, queryset=JobExecution.objects.all()).qs

        assert [e.trigger_source for e in qs] == ["manual"]

    def test_filter_by_trigger_source_multi_comma(self):
        """按多个触发来源（逗号分隔）过滤"""
        self._make(trigger_source=TriggerSource.MANUAL)
        self._make(trigger_source=TriggerSource.SCHEDULED)
        self._make(trigger_source=TriggerSource.API)

        qs = JobExecutionFilter({"trigger_source": "manual,scheduled"}, queryset=JobExecution.objects.all()).qs

        assert sorted(e.trigger_source for e in qs) == ["manual", "scheduled"]
