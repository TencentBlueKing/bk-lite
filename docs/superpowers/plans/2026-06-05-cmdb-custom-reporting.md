# CMDB Custom Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new CMDB custom-reporting module that lets customer scripts push arbitrary object data into CMDB through task-scoped HTTP ingestion while reusing existing merge, relation, cleanup, and change-record semantics.

**Architecture:** Keep automatic discovery and custom reporting separate at the task/product layer, but reuse the existing CMDB model-management, instance merge, relation persistence, and change-record paths under the hood. Implement custom reporting as a new backend domain (`task + credential + batch + pending relation + review`) and a new web module under `CMDB > 管理`, with quick-model creation embedded in the task wizard.

**Tech Stack:** Python 3.12, Django 4.2, DRF, existing CMDB FalkorDB-backed services, existing pytest suite in `server/apps/cmdb/tests`, Next.js App Router, React, TypeScript, Ant Design, existing CMDB i18n/menu/api patterns.

---

## File Structure

### Backend: new custom-reporting domain

- Create: `server/apps/cmdb/models/custom_reporting.py` — task, credential, batch, pending relation, cleanup review models.
- Modify: `server/apps/cmdb/models/__init__.py` — export the new models.
- Modify: `server/apps/cmdb/models/change_record.py` — add `CUSTOM_REPORTING_CHANGE` scenario constant and choice entry.
- Create: `server/apps/cmdb/serializers/custom_reporting.py` — task CRUD serializer, ingest payload serializer, batch/review/document serializers.
- Create: `server/apps/cmdb/services/custom_reporting_task_service.py` — task CRUD, credential rotation/revoke, quick-model bootstrap.
- Create: `server/apps/cmdb/services/custom_reporting_ingest_service.py` — ingest orchestration, field auto-registration, merge dispatch, pending relation creation, batch summarization.
- Create: `server/apps/cmdb/services/custom_reporting_document_service.py` — task-specific onboarding document builder.
- Create: `server/apps/cmdb/views/custom_reporting.py` — admin CRUD endpoints plus ingest/review/document endpoints.
- Modify: `server/apps/cmdb/urls.py` — register the new viewset/router.
- Create: `server/apps/cmdb/migrations/0024_custom_reporting.py` — schema for the new Django models.
- Modify: `server/apps/cmdb/language/zh-Hans.yaml` — scenario labels, task status labels, quick-model labels.

### Backend: existing CMDB reuse points

- Modify: `server/apps/cmdb/services/model.py` — add helper hooks for quick-model bootstrap / field auto-registration using existing model storage semantics.
- Modify: `server/apps/cmdb/services/instance.py` — expose a reusable merge entrypoint for custom-reporting writes instead of routing only through collect-task code paths.
- Modify: `server/apps/cmdb/services/auto_relation_rule.py` — ensure rules only execute when the target model is a formal model.
- Modify: `server/apps/cmdb/utils/change_record.py` — support custom-reporting scenario plumbing where needed.

### Backend tests (existing files only)

- Modify: `server/apps/cmdb/tests/test_models.py`
- Modify: `server/apps/cmdb/tests/test_serializers.py`
- Modify: `server/apps/cmdb/tests/test_model_views.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_change_record_views.py`

### Frontend

- Create: `web/src/app/cmdb/api/customReporting.ts` — custom-reporting API hooks.
- Modify: `web/src/app/cmdb/api/index.ts` — export the new API hook.
- Create: `web/src/app/cmdb/types/customReporting.ts` — task, batch, quick-model, ingest-doc, review types.
- Modify: `web/src/app/cmdb/constants/menu.json` — add the new menu item.
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx` — module shell page.
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskTable.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskDetail.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/batchReviewDrawer.tsx`

## Task 0: Prepare the execution workspace and freeze the baseline

**Files:**
- Read: `docs/superpowers/specs/2026-06-05-cmdb-custom-reporting-design.md`
- Validate: `server/apps/cmdb/tests/test_models.py`
- Validate: `server/apps/cmdb/tests/test_serializers.py`
- Validate: `server/apps/cmdb/tests/test_misc_views.py`
- Validate: `web/src/app/cmdb/api/index.ts`

- [ ] **Step 1: Create an isolated worktree before any implementation**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
# REQUIRED SUB-SKILL during execution: superpowers:using-git-worktrees
git worktree list
```

Run: invoke `superpowers:using-git-worktrees` from the execution session before touching code.

Expected: a fresh worktree path dedicated to this feature, with the current branch state available and no unrelated working-tree changes mixed into implementation.

- [ ] **Step 2: Run the backend baseline tests that this feature will extend**

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_models.py \
  apps/cmdb/tests/test_serializers.py \
  apps/cmdb/tests/test_model_views.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_change_record_views.py -v
```

Expected: PASS on the baseline branch before custom-reporting changes start.

- [ ] **Step 3: Run the frontend baseline validation**

```bash
cd web
pnpm lint
pnpm type-check
```

Expected: PASS on the baseline branch before custom-reporting changes start.

- [ ] **Step 4: Commit the baseline checkpoint**

```bash
git status --short
git commit --allow-empty -m "chore: checkpoint CMDB custom reporting baseline"
```

Expected: an empty checkpoint commit exists in the isolated worktree so later bisects have a known “before feature” anchor.

## Task 1: Add the backend domain model and admin API skeleton

**Files:**
- Create: `server/apps/cmdb/models/custom_reporting.py`
- Modify: `server/apps/cmdb/models/__init__.py`
- Modify: `server/apps/cmdb/models/change_record.py`
- Create: `server/apps/cmdb/serializers/custom_reporting.py`
- Create: `server/apps/cmdb/views/custom_reporting.py`
- Modify: `server/apps/cmdb/urls.py`
- Create: `server/apps/cmdb/migrations/0024_custom_reporting.py`
- Modify: `server/apps/cmdb/tests/test_models.py`
- Modify: `server/apps/cmdb/tests/test_serializers.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_change_record_views.py`

- [ ] **Step 1: Write the failing backend model/view tests**

```python
# server/apps/cmdb/tests/test_models.py
@pytest.mark.django_db
def test_custom_reporting_task_name_is_unique_within_team():
    from apps.cmdb.models.custom_reporting import CustomReportingTask

    CustomReportingTask.objects.create(
        name='业务系统A',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['inst_name'],
        cleanup_strategy='no_cleanup',
    )

    with pytest.raises(Exception):
        CustomReportingTask.objects.create(
            name='业务系统A',
            team=[1],
            model_mode='standard',
            model_id='host',
            identity_keys=['inst_name'],
            cleanup_strategy='no_cleanup',
        )
```

```python
# server/apps/cmdb/tests/test_serializers.py
def test_custom_reporting_task_serializer_requires_quick_model_identity_keys():
    from apps.cmdb.serializers.custom_reporting import CustomReportingTaskSerializer

    serializer = CustomReportingTaskSerializer(
        data={
            'name': 'quick-app',
            'team': [1],
            'model_mode': 'quick',
            'quick_model_name': '业务系统',
            'identity_keys': [],
            'cleanup_strategy': 'snapshot_cleanup',
            'snapshot_delete_ratio_threshold': 30,
        }
    )
    assert not serializer.is_valid()
    assert 'identity_keys' in serializer.errors
```

```python
# server/apps/cmdb/tests/test_misc_views.py
@pytest.mark.django_db
def test_custom_reporting_task_viewset_lists_current_team_tasks(authenticated_user):
    from rest_framework.test import APIRequestFactory, force_authenticate
    from apps.cmdb.models.custom_reporting import CustomReportingTask
    from apps.cmdb.views.custom_reporting import CustomReportingTaskViewSet

    CustomReportingTask.objects.create(
        name='task-a',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['inst_name'],
        cleanup_strategy='no_cleanup',
    )
    factory = APIRequestFactory()
    request = factory.get('/cmdb/api/custom_reporting/tasks/')
    request.COOKIES['current_team'] = '1'
    force_authenticate(request, user=authenticated_user)
    response = CustomReportingTaskViewSet.as_view({'get': 'list'})(request)
    assert response.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_models.py \
  apps/cmdb/tests/test_serializers.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_change_record_views.py -v
```

Expected: FAIL because the custom-reporting models, serializer, viewset, route, and change-record scenario do not exist yet.

- [ ] **Step 3: Implement the minimal backend domain and route skeleton**

```python
# server/apps/cmdb/models/custom_reporting.py
from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CustomReportingTask(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, help_text='任务名称')
    team = JSONField(default=list, help_text='关联组织')
    model_mode = models.CharField(max_length=16, choices=[('standard', '完整模型'), ('quick', '快速模型')])
    model_id = models.CharField(max_length=64, blank=True, default='')
    quick_model_name = models.CharField(max_length=128, blank=True, default='')
    identity_keys = JSONField(default=list, help_text='身份键')
    cleanup_strategy = models.CharField(max_length=32, help_text='清理策略')
    expire_days = models.PositiveSmallIntegerField(default=0)
    snapshot_delete_ratio_threshold = models.PositiveSmallIntegerField(default=0)
    credential_status = models.CharField(max_length=16, default='active')
    last_reported_at = models.DateTimeField(blank=True, null=True)
    doc_version = models.PositiveIntegerField(default=1)
```

```python
# server/apps/cmdb/serializers/custom_reporting.py
class CustomReportingTaskSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        duplicated = CustomReportingTask.objects.filter(name=attrs['name'])
        duplicated = [
            task for task in duplicated
            if set(task.team or []) & set(attrs.get('team') or [])
        ]
        if duplicated and not self.instance:
            raise serializers.ValidationError({'name': '同一组织内任务名称必须唯一'})
        return attrs
```

```python
# server/apps/cmdb/models/change_record.py
CUSTOM_REPORTING_CHANGE = 'custom_reporting_change'

SCENARIO_CHOICES = [
    (DEVICE_LIFECYCLE, '设备流转'),
    (RELATION_CHANGE, '关系变更'),
    (ORDINARY_ATTRIBUTE_CHANGE, '普通属性变更'),
    (COLLECT_AUTOMATION_CHANGE, '自动采集'),
    (CUSTOM_REPORTING_CHANGE, '自定义上报'),
    (MODEL_MANAGEMENT_CHANGE, '模型管理变更'),
]
```

```python
# server/apps/cmdb/views/custom_reporting.py
class CustomReportingTaskViewSet(AuthViewSet):
    queryset = CustomReportingTask.objects.all().order_by('-updated_at')
    serializer_class = CustomReportingTaskSerializer

    @HasPermission('custom_reporting-View')
    def list(self, request, *args, **kwargs):
        queryset = self.queryset.filter(team__contains=[int(request.COOKIES.get('current_team', '0'))])
        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success({'items': serializer.data, 'count': len(serializer.data)})
```

```python
# server/apps/cmdb/urls.py
from apps.cmdb.views.custom_reporting import CustomReportingTaskViewSet

router.register(r'api/custom_reporting/tasks', CustomReportingTaskViewSet, basename='custom_reporting_task')
```

- [ ] **Step 4: Run the tests to verify the skeleton passes**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_models.py \
  apps/cmdb/tests/test_serializers.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_change_record_views.py -v
```

Expected: PASS for the new task model, serializer validation, route registration, and change-record enum exposure.

- [ ] **Step 5: Commit**

```bash
git add \
  server/apps/cmdb/models/custom_reporting.py \
  server/apps/cmdb/models/__init__.py \
  server/apps/cmdb/models/change_record.py \
  server/apps/cmdb/serializers/custom_reporting.py \
  server/apps/cmdb/views/custom_reporting.py \
  server/apps/cmdb/urls.py \
  server/apps/cmdb/migrations/0024_custom_reporting.py \
  server/apps/cmdb/tests/test_models.py \
  server/apps/cmdb/tests/test_serializers.py \
  server/apps/cmdb/tests/test_misc_views.py \
  server/apps/cmdb/tests/test_change_record_views.py
git commit -m "feat: add custom reporting task domain"
```

## Task 2: Add credential rotation, quick-model bootstrap, and task-level onboarding docs

**Files:**
- Modify: `server/apps/cmdb/models/custom_reporting.py`
- Create: `server/apps/cmdb/services/custom_reporting_task_service.py`
- Create: `server/apps/cmdb/services/custom_reporting_document_service.py`
- Modify: `server/apps/cmdb/services/model.py`
- Modify: `server/apps/cmdb/views/custom_reporting.py`
- Modify: `server/apps/cmdb/serializers/custom_reporting.py`
- Modify: `server/apps/cmdb/tests/test_models.py`
- Modify: `server/apps/cmdb/tests/test_model_views.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`

- [ ] **Step 1: Write the failing service/view tests**

```python
# server/apps/cmdb/tests/test_model_views.py
@pytest.mark.django_db
def test_create_custom_reporting_quick_model_task_bootstraps_model(authenticated_user, monkeypatch):
    from rest_framework.test import APIRequestFactory, force_authenticate
    from apps.cmdb.views.custom_reporting import CustomReportingTaskViewSet

    created = {}

    def fake_create_quick_model(*, name, identity_keys, team, username):
        created.update({'name': name, 'identity_keys': identity_keys, 'team': team, 'username': username})
        return 'quick_app'

    monkeypatch.setattr(
        'apps.cmdb.services.custom_reporting_task_service.CustomReportingTaskService.create_quick_model',
        staticmethod(fake_create_quick_model),
    )

    factory = APIRequestFactory()
    request = factory.post('/cmdb/api/custom_reporting/tasks/', {
        'name': 'app-task',
        'team': [1],
        'model_mode': 'quick',
        'quick_model_name': '业务系统',
        'identity_keys': ['app_code'],
        'cleanup_strategy': 'no_cleanup',
    }, format='json')
    request.COOKIES['current_team'] = '1'
    force_authenticate(request, user=authenticated_user)
    response = CustomReportingTaskViewSet.as_view({'post': 'create'})(request)
    assert response.status_code == 200
    assert created['identity_keys'] == ['app_code']
```

```python
# server/apps/cmdb/tests/test_misc_views.py
@pytest.mark.django_db
def test_rotate_custom_reporting_token_invalidates_previous_digest(authenticated_user):
    from apps.cmdb.models.custom_reporting import CustomReportingTask

    task = CustomReportingTask.objects.create(
        name='rotate-task',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['inst_name'],
        cleanup_strategy='no_cleanup',
    )
    task.set_credential(raw_token='raw-task-token', operator=authenticated_user.username)
    old_digest = task.credential.token_hash
    task.rotate_credential(operator=authenticated_user.username)
    assert task.credential.token_hash != old_digest
    assert task.credential.revoked_at is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_model_views.py \
  apps/cmdb/tests/test_misc_views.py -v
```

Expected: FAIL because quick-model bootstrap helpers, credential rotation, and onboarding-document endpoints are not implemented.

- [ ] **Step 3: Implement the task service, credential lifecycle, and onboarding docs**

```python
# server/apps/cmdb/services/custom_reporting_task_service.py
from django.utils import timezone
from nanoid import generate
from django.db import transaction


class CustomReportingTaskService:
    @staticmethod
    def issue_token():
        return generate(size=40)

    @classmethod
    @transaction.atomic
    def create_task(cls, *, data, username):
        model_id = data.get('model_id', '')
        if data['model_mode'] == 'quick':
            model_id = cls.create_quick_model(
                name=data['quick_model_name'],
                identity_keys=data['identity_keys'],
                team=data['team'],
                username=username,
            )
        task = CustomReportingTask.objects.create(
            name=data['name'],
            team=data['team'],
            model_mode=data['model_mode'],
            model_id=model_id,
            quick_model_name=data.get('quick_model_name', ''),
            identity_keys=data['identity_keys'],
            cleanup_strategy=data['cleanup_strategy'],
            expire_days=data.get('expire_days', 0),
            snapshot_delete_ratio_threshold=data.get('snapshot_delete_ratio_threshold', 0),
        )
        raw_token = cls.issue_token()
        task.set_credential(raw_token=raw_token, operator=username)
        return task, raw_token
```

```python
# server/apps/cmdb/services/custom_reporting_document_service.py
class CustomReportingDocumentService:
    @staticmethod
    def build_task_document(task):
        return {
            'endpoint': f'/api/proxy/cmdb/api/custom_reporting/tasks/{task.id}/ingest/',
            'auth_header': 'Authorization: Bearer <task-token>',
            'task_name': task.name,
            'model_mode': task.model_mode,
            'model_id': task.model_id,
            'identity_keys': task.identity_keys,
            'payload_example': {
                'instances': [{'identity': {'app_code': 'demo'}, 'attributes': {'name': 'Demo App'}}],
                'relations': [],
                'batch_metadata': {'source': 'customer-script'},
            },
        }
```

```python
# server/apps/cmdb/views/custom_reporting.py
@action(methods=['post'], detail=True, url_path='rotate_credential')
def rotate_credential(self, request, pk=None):
    task = self.get_object()
    raw_token = CustomReportingTaskService.rotate_credential(task=task, operator=request.user.username)
    return WebUtils.response_success({'token': raw_token})

@action(methods=['post'], detail=True, url_path='revoke_credential')
def revoke_credential(self, request, pk=None):
    task = self.get_object()
    CustomReportingTaskService.revoke_credential(task=task, operator=request.user.username)
    return WebUtils.response_success()

@action(methods=['get'], detail=True, url_path='document')
def document(self, request, pk=None):
    task = self.get_object()
    return WebUtils.response_success(CustomReportingDocumentService.build_task_document(task))
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_models.py \
  apps/cmdb/tests/test_model_views.py \
  apps/cmdb/tests/test_misc_views.py -v
```

Expected: PASS with quick-model bootstrap, credential rotation/revoke, and task-document generation covered.

- [ ] **Step 5: Commit**

```bash
git add \
  server/apps/cmdb/models/custom_reporting.py \
  server/apps/cmdb/services/custom_reporting_task_service.py \
  server/apps/cmdb/services/custom_reporting_document_service.py \
  server/apps/cmdb/services/model.py \
  server/apps/cmdb/views/custom_reporting.py \
  server/apps/cmdb/serializers/custom_reporting.py \
  server/apps/cmdb/tests/test_models.py \
  server/apps/cmdb/tests/test_model_views.py \
  server/apps/cmdb/tests/test_misc_views.py
git commit -m "feat: add custom reporting credential and quick model flows"
```

## Task 3: Implement ingest, batch tracking, field auto-registration, and change-record plumbing

**Files:**
- Create: `server/apps/cmdb/services/custom_reporting_ingest_service.py`
- Modify: `server/apps/cmdb/models/custom_reporting.py`
- Modify: `server/apps/cmdb/services/model.py`
- Modify: `server/apps/cmdb/services/instance.py`
- Modify: `server/apps/cmdb/utils/change_record.py`
- Modify: `server/apps/cmdb/views/custom_reporting.py`
- Modify: `server/apps/cmdb/serializers/custom_reporting.py`
- Modify: `server/apps/cmdb/tests/test_serializers.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_change_record_views.py`

- [ ] **Step 1: Write the failing ingest tests**

```python
# server/apps/cmdb/tests/test_misc_views.py
@pytest.mark.django_db
def test_ingest_creates_batch_and_updates_last_reported_at(authenticated_user, monkeypatch):
    from rest_framework.test import APIRequestFactory
    from apps.cmdb.models.custom_reporting import CustomReportingTask
    from apps.cmdb.views.custom_reporting import CustomReportingTaskViewSet

    task = CustomReportingTask.objects.create(
        name='ingest-task',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['app_code'],
        cleanup_strategy='no_cleanup',
    )
    task.set_credential(raw_token='raw-task-token', operator=authenticated_user.username)

    monkeypatch.setattr(
        'apps.cmdb.services.custom_reporting_ingest_service.CustomReportingIngestService.ingest',
        staticmethod(lambda **kwargs: {'batch_status': 'success', 'created': 1, 'updated': 0, 'deleted': 0, 'errors': 0}),
    )

    factory = APIRequestFactory()
    request = factory.post(
        f'/cmdb/api/custom_reporting/tasks/{task.id}/ingest/',
        {
            'instances': [{'identity': {'app_code': 'demo'}, 'attributes': {'name': 'Demo App'}}],
            'relations': [],
            'batch_metadata': {'source': 'script'},
        },
        format='json',
        HTTP_AUTHORIZATION='Bearer raw-task-token',
    )
    response = CustomReportingTaskViewSet.as_view({'post': 'ingest'})(request, pk=task.id)
    assert response.status_code == 200
```

```python
# server/apps/cmdb/tests/test_change_record_views.py
@pytest.mark.django_db
def test_change_record_enum_contains_custom_reporting(superuser):
    response = ChangeRecordViewSet.as_view({'get': 'enum_scenarios'})(_req('get', superuser))
    body = _body(response)
    assert 'custom_reporting_change' in body['data']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_serializers.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_change_record_views.py -v
```

Expected: FAIL because there is no ingest serializer, no task-scoped token auth, no batch persistence, and no custom-reporting change-record path.

- [ ] **Step 3: Implement the minimal ingest pipeline**

```python
# server/apps/cmdb/services/custom_reporting_ingest_service.py
from django.db import transaction
from django.utils import timezone


class CustomReportingIngestService:
    @classmethod
    @transaction.atomic
    def ingest(cls, *, task, payload, operator='custom-reporting'):
        batch = task.create_batch(payload=payload)
        identity_keys = task.identity_keys
        instances = payload.get('instances', [])
        created = updated = errors = 0

        if task.model_mode == 'quick':
            cls.ensure_quick_model_fields(task=task, instances=instances)

        for item in instances:
            identity = item.get('identity', {})
            attrs = item.get('attributes', {})
            result = cls.merge_instance(task=task, identity=identity, attributes=attrs, operator=operator)
            created += int(result == 'created')
            updated += int(result == 'updated')

        batch.mark_finished(
            status='success' if errors == 0 else 'partial_success',
            summary_counts={'created': created, 'updated': updated, 'deleted': 0, 'errors': errors},
        )
        task.last_reported_at = timezone.now()
        task.save(update_fields=['last_reported_at', 'updated_at'])
        return {'batch_status': batch.status, 'created': created, 'updated': updated, 'deleted': 0, 'errors': errors}
```

```python
# server/apps/cmdb/views/custom_reporting.py
@action(methods=['post'], detail=True, url_path='ingest', authentication_classes=[], permission_classes=[])
def ingest(self, request, pk=None):
    task = self.get_object()
    serializer = CustomReportingIngestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    task.assert_bearer_token(request.headers.get('Authorization', ''))
    result = CustomReportingIngestService.ingest(task=task, payload=serializer.validated_data)
    return WebUtils.response_success(result)
```

```python
# server/apps/cmdb/utils/change_record.py
create_change_record(
    operator=operator,
    model_id=task.model_id,
    label='自定义上报',
    _type=UPDATE_INST,
    message=f'自定义上报更新实例: {identity}',
    inst_id=inst_id,
    model_object='自定义上报',
    scenario=CUSTOM_REPORTING_CHANGE,
)
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_serializers.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_change_record_views.py -v
```

Expected: PASS with ingest request validation, batch creation, `last_reported_at` refresh, and change-record scenario registration covered.

- [ ] **Step 5: Commit**

```bash
git add \
  server/apps/cmdb/services/custom_reporting_ingest_service.py \
  server/apps/cmdb/models/custom_reporting.py \
  server/apps/cmdb/services/model.py \
  server/apps/cmdb/services/instance.py \
  server/apps/cmdb/utils/change_record.py \
  server/apps/cmdb/views/custom_reporting.py \
  server/apps/cmdb/serializers/custom_reporting.py \
  server/apps/cmdb/tests/test_serializers.py \
  server/apps/cmdb/tests/test_misc_views.py \
  server/apps/cmdb/tests/test_change_record_views.py
git commit -m "feat: add custom reporting ingest pipeline"
```

## Task 4: Add relation reconciliation, cleanup strategy execution, and review state handling

**Files:**
- Modify: `server/apps/cmdb/services/custom_reporting_ingest_service.py`
- Modify: `server/apps/cmdb/models/custom_reporting.py`
- Modify: `server/apps/cmdb/services/auto_relation_rule.py`
- Modify: `server/apps/cmdb/views/custom_reporting.py`
- Modify: `server/apps/cmdb/serializers/custom_reporting.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_models.py`

- [ ] **Step 1: Write the failing relation/cleanup tests**

```python
# server/apps/cmdb/tests/test_misc_views.py
@pytest.mark.django_db
def test_ingest_stores_pending_relation_when_target_not_found():
    from apps.cmdb.models.custom_reporting import CustomReportingTask

    task = CustomReportingTask.objects.create(
        name='relation-task',
        team=[1],
        model_mode='standard',
        model_id='app_model',
        identity_keys=['app_code'],
        cleanup_strategy='no_cleanup',
    )
    payload = {
        'instances': [{'identity': {'app_code': 'demo'}, 'attributes': {'name': 'Demo App'}}],
        'relations': [{
            'source_identity': {'app_code': 'demo'},
            'relation_type': 'runs_on',
            'target_model_id': 'host',
            'target_identity': {'inst_name': 'host-a'},
        }],
        'batch_metadata': {},
    }
    result = CustomReportingIngestService.ingest(task=task, payload=payload)
    assert result['pending_relations'] == 1
```

```python
# server/apps/cmdb/tests/test_models.py
@pytest.mark.django_db
def test_snapshot_cleanup_enters_pending_review_when_delete_ratio_exceeds_threshold():
    from apps.cmdb.models.custom_reporting import CustomReportingTask

    task = CustomReportingTask.objects.create(
        name='snapshot-task',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['inst_name'],
        cleanup_strategy='snapshot_cleanup',
        snapshot_delete_ratio_threshold=30,
    )
    review = task.evaluate_snapshot_cleanup(total_scope=10, delete_candidates=5)
    assert review.status == 'pending_review'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_models.py -v
```

Expected: FAIL because pending relations, cleanup review evaluation, and review endpoints are not implemented.

- [ ] **Step 3: Implement relation reconciliation and cleanup review**

```python
# server/apps/cmdb/services/custom_reporting_ingest_service.py
def process_relations(cls, *, task, batch, payload, instance_index):
    pending_count = 0
    for relation in payload.get('relations', []):
        target_inst = cls.resolve_target_instance(
            target_model_id=relation['target_model_id'],
            target_identity=relation['target_identity'],
            instance_index=instance_index,
        )
        if target_inst is None:
            task.pending_relations.create(
                batch=batch,
                source_identity=relation['source_identity'],
                relation_type=relation['relation_type'],
                target_model_id=relation['target_model_id'],
                target_identity=relation['target_identity'],
            )
            pending_count += 1
            continue
        cls.bind_relation(
            source_identity=relation['source_identity'],
            relation_type=relation['relation_type'],
            target_instance=target_inst,
            model_id=task.model_id,
        )
    return pending_count
```

```python
# server/apps/cmdb/models/custom_reporting.py
def evaluate_snapshot_cleanup(self, *, total_scope, delete_candidates):
    ratio = 0 if total_scope == 0 else int(delete_candidates * 100 / total_scope)
    if ratio > self.snapshot_delete_ratio_threshold:
        return CustomReportingReview.objects.create(task=self, status='pending_review', delete_ratio=ratio)
    return None
```

```python
# server/apps/cmdb/views/custom_reporting.py
@action(methods=['post'], detail=True, url_path='reviews/(?P<review_id>[^/.]+)/approve')
def approve_review(self, request, pk=None, review_id=None):
    review = self.get_object().reviews.get(pk=review_id)
    review.approve(operator=request.user.username)
    return WebUtils.response_success()
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_models.py -v
```

Expected: PASS with pending relation persistence, snapshot threshold review, and manual approval entrypoint covered.

- [ ] **Step 5: Commit**

```bash
git add \
  server/apps/cmdb/services/custom_reporting_ingest_service.py \
  server/apps/cmdb/models/custom_reporting.py \
  server/apps/cmdb/services/auto_relation_rule.py \
  server/apps/cmdb/views/custom_reporting.py \
  server/apps/cmdb/serializers/custom_reporting.py \
  server/apps/cmdb/tests/test_misc_views.py \
  server/apps/cmdb/tests/test_models.py
git commit -m "feat: add custom reporting relation and cleanup review flows"
```

## Task 5: Add the CMDB web module, route entry, and task/detail UI

**Files:**
- Create: `web/src/app/cmdb/api/customReporting.ts`
- Modify: `web/src/app/cmdb/api/index.ts`
- Create: `web/src/app/cmdb/types/customReporting.ts`
- Modify: `web/src/app/cmdb/constants/menu.json`
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskTable.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskDetail.tsx`
- Create: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/batchReviewDrawer.tsx`

- [ ] **Step 1: Write the failing type/page expectations**

```ts
// web/src/app/cmdb/types/customReporting.ts
export interface CustomReportingTask {
  id: number;
  name: string;
  modelMode: 'standard' | 'quick';
  modelId: string;
  identityKeys: string[];
  cleanupStrategy: 'no_cleanup' | 'expire_cleanup' | 'snapshot_cleanup';
  lastReportedAt: string | null;
  credentialStatus: 'active' | 'revoked';
}
```

```tsx
// web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx
export default function CustomReportingPage() {
  return <div data-testid="custom-reporting-page">custom reporting</div>
}
```

Expected compile failure before implementation: imports from `@/app/cmdb/api/customReporting` and `@/app/cmdb/types/customReporting` do not exist.

- [ ] **Step 2: Run frontend validation to verify it fails**

Run:

```bash
cd web
pnpm type-check
```

Expected: FAIL because the new API/type/page modules and menu references do not exist.

- [ ] **Step 3: Implement the web API and UI shell**

```ts
// web/src/app/cmdb/api/customReporting.ts
import useApiClient from '@/utils/request'

export const useCustomReportingApi = () => {
  const { get, post, put, del } = useApiClient()

  return {
    getTaskList: (params?: Record<string, unknown>) => get('/cmdb/api/custom_reporting/tasks/', { params }),
    createTask: (params: Record<string, unknown>) => post('/cmdb/api/custom_reporting/tasks/', params),
    updateTask: (taskId: string | number, params: Record<string, unknown>) => put(`/cmdb/api/custom_reporting/tasks/${taskId}/`, params),
    deleteTask: (taskId: string | number) => del(`/cmdb/api/custom_reporting/tasks/${taskId}/`),
    rotateCredential: (taskId: string | number) => post(`/cmdb/api/custom_reporting/tasks/${taskId}/rotate_credential/`),
    revokeCredential: (taskId: string | number) => post(`/cmdb/api/custom_reporting/tasks/${taskId}/revoke_credential/`),
    getTaskDocument: (taskId: string | number) => get(`/cmdb/api/custom_reporting/tasks/${taskId}/document/`),
  }
}
```

```tsx
// web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx
'use client'

import { useState } from 'react'
import Introduction from '@/app/cmdb/components/introduction'
import TaskTable from './components/taskTable'
import TaskWizard from './components/taskWizard'
import TaskDetail from './components/taskDetail'

export default function CustomReportingPage() {
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null)
  const [detailTaskId, setDetailTaskId] = useState<number | null>(null)

  return (
    <div className="flex h-full flex-col">
      <Introduction title="自定义上报" message="客户脚本主动推送数据进入 CMDB 的统一通道" />
      <TaskTable onCreate={() => setEditingTaskId(0)} onView={setDetailTaskId} onEdit={setEditingTaskId} />
      <TaskWizard open={editingTaskId !== null} taskId={editingTaskId} onClose={() => setEditingTaskId(null)} />
      <TaskDetail open={detailTaskId !== null} taskId={detailTaskId} onClose={() => setDetailTaskId(null)} />
    </div>
  )
}
```

```json
// web/src/app/cmdb/constants/menu.json
{
  "title": "自定义上报",
  "icon": "shujumoxingguanli",
  "url": "/cmdb/assetManage/customReporting",
  "name": "custom_reporting"
}
```

- [ ] **Step 4: Run frontend validation**

Run:

```bash
cd web
pnpm lint
pnpm type-check
```

Expected: PASS with the new menu entry, API hook, type definitions, and page shell compiled.

- [ ] **Step 5: Commit**

```bash
git add \
  web/src/app/cmdb/api/customReporting.ts \
  web/src/app/cmdb/api/index.ts \
  web/src/app/cmdb/types/customReporting.ts \
  web/src/app/cmdb/constants/menu.json \
  web/src/app/cmdb/locales/zh.json \
  web/src/app/cmdb/locales/en.json \
  web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskTable.tsx \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskDetail.tsx \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/batchReviewDrawer.tsx
git commit -m "feat: add CMDB custom reporting UI"
```

## Task 6: Wire the full flow end to end and perform final verification

**Files:**
- Modify: `server/apps/cmdb/tests/test_models.py`
- Modify: `server/apps/cmdb/tests/test_serializers.py`
- Modify: `server/apps/cmdb/tests/test_model_views.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_change_record_views.py`
- Modify: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskDetail.tsx`

- [ ] **Step 1: Add the final integration-focused regression cases**

```python
# server/apps/cmdb/tests/test_misc_views.py
@pytest.mark.django_db
def test_custom_reporting_snapshot_over_threshold_returns_pending_review():
    from apps.cmdb.models.custom_reporting import CustomReportingTask

    task = CustomReportingTask.objects.create(
        name='snapshot-pending-task',
        team=[1],
        model_mode='standard',
        model_id='host',
        identity_keys=['inst_name'],
        cleanup_strategy='snapshot_cleanup',
        snapshot_delete_ratio_threshold=10,
    )
    payload = {
        'instances': [],
        'relations': [],
        'batch_metadata': {'source': 'script'},
    }
    result = CustomReportingIngestService.ingest(task=task, payload=payload)
    assert result['batch_status'] == 'pending_review'
```

```tsx
// web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx
const cleanupOptions = [
  { label: '不删除', value: 'no_cleanup' },
  { label: '过期清理', value: 'expire_cleanup' },
  { label: '快照清理', value: 'snapshot_cleanup' },
]
```

- [ ] **Step 2: Run the full backend verification**

Run:

```bash
cd server
make test
```

Expected: PASS with the full `server/apps/cmdb` suite still green after the custom-reporting feature lands.

- [ ] **Step 3: Run the full frontend verification**

Run:

```bash
cd web
pnpm lint
pnpm type-check
```

Expected: PASS with no type regressions from the new custom-reporting module.

- [ ] **Step 4: Run the required completion gate**

```text
Invoke superpowers:verification-before-completion before claiming the feature is done.
```

Expected: the implementation session re-runs the evidence-producing checks above, confirms outputs, and only then reports completion.

- [ ] **Step 5: Commit**

```bash
git add \
  server/apps/cmdb/tests/test_models.py \
  server/apps/cmdb/tests/test_serializers.py \
  server/apps/cmdb/tests/test_model_views.py \
  server/apps/cmdb/tests/test_misc_views.py \
  server/apps/cmdb/tests/test_change_record_views.py \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskWizard.tsx \
  web/src/app/cmdb/(pages)/assetManage/customReporting/components/taskDetail.tsx
git commit -m "test: finalize CMDB custom reporting verification"
```

## Self-Review

1. **Spec coverage:** The tasks cover task CRUD, quick model creation, task credential lifecycle, ingest API, field auto-registration, relation reconciliation, cleanup review, change-record scenario, onboarding docs, menu/route/page work, and final verification. No spec section is left without a delivery task.
2. **Placeholder scan:** No `TBD`, `TODO`, “implement later”, or “similar to Task N” placeholders remain. Every code-changing step includes concrete code and every validation step includes exact commands.
3. **Type consistency:** The plan consistently uses `CustomReportingTask`, `CustomReportingCredential`, `CustomReportingBatch`, `CustomReportingIngestService`, `model_mode`, `identity_keys`, `cleanup_strategy`, and `snapshot_delete_ratio_threshold` across backend and frontend tasks.
