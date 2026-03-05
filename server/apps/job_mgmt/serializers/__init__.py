from apps.job_mgmt.serializers.dangerous_path import DangerousPathCreateSerializer, DangerousPathSerializer, DangerousPathUpdateSerializer  # noqa
from apps.job_mgmt.serializers.dangerous_rule import DangerousRuleCreateSerializer, DangerousRuleSerializer, DangerousRuleUpdateSerializer  # noqa
from apps.job_mgmt.serializers.dashboard import DashboardRecentExecutionSerializer, DashboardStatsSerializer, DashboardTrendSerializer  # noqa
from apps.job_mgmt.serializers.execution import (  # noqa
    FileDistributionSerializer,
    JobExecutionDetailSerializer,
    JobExecutionListSerializer,
    JobExecutionTargetSerializer,
    PlaybookExecuteSerializer,
    QuickExecuteSerializer,
)
from apps.job_mgmt.serializers.playbook import (  # noqa
    PlaybookBatchDeleteSerializer,
    PlaybookCreateSerializer,
    PlaybookSerializer,
    PlaybookUpdateSerializer,
)
from apps.job_mgmt.serializers.scheduled_task import (  # noqa
    ScheduledTaskBatchDeleteSerializer,
    ScheduledTaskCreateSerializer,
    ScheduledTaskDetailSerializer,
    ScheduledTaskListSerializer,
    ScheduledTaskToggleSerializer,
    ScheduledTaskUpdateSerializer,
)
from apps.job_mgmt.serializers.script import ScriptBatchDeleteSerializer, ScriptCreateSerializer, ScriptSerializer, ScriptUpdateSerializer  # noqa
from apps.job_mgmt.serializers.target import (  # noqa
    TargetBatchDeleteSerializer,
    TargetCreateSerializer,
    TargetSerializer,
    TargetTestConnectionSerializer,
    TargetUpdateSerializer,
)
