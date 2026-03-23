# CMDB 数据订阅 - Tech Plan

日期：2026-03-16

## 技术目标与非目标

### 技术目标
- 在现有 CMDB 架构内新增"数据订阅"能力，不新增服务、不改动跨模块架构
- 落地订阅规则模型 `SubscriptionRule`，支持 CRUD 与组织权限控制
- 落地三类触发检测：属性变化（基于 ChangeRecord）、关联变化（基于快照对比）、临近到期（基于时间字段扫描）
- 落地 Celery Beat 定时任务（2 分钟周期）轮询检查，不依赖 Django Signal
- 落地 Redis 聚合窗口（1 分钟）防打扰策略
- 落地通知发送：复用 `system_mgmt.nats_api.send_msg_with_channel()` 发送消息
- 落地前端规则管理抽屉、四个快速订阅入口、权限态展示

### 非目标
- 不支持跨组织/跨租户订阅
- 不支持多跳关联链路订阅（仅一跳）
- 不新增通知渠道类型
- 不实现审批流、版本管理、订阅模板市场

---

## 1) 文件与目录结构 (File Tree)

> `A`=新增，`M`=修改

### 1.1 后端文件

```text
server/
└─ apps/cmdb/
   ├─ urls.py                                                    (M) 注册 subscription 路由
   ├─ constants/
   │  └─ subscription.py                                         (A) 订阅相关常量定义
   ├─ models/
   │  ├─ __init__.py                                             (M) 导出 SubscriptionRule
   │  └─ subscription_rule.py                                    (A) 订阅规则模型
   ├─ serializers/
   │  └─ subscription.py                                         (A) 序列化器
   ├─ views/
   │  └─ subscription.py                                         (A) ViewSet
   ├─ services/
   │  └─ subscription_trigger.py                                 (A) 触发检测服务
   └─ tasks/
      └─ celery_tasks.py                                         (M) 新增定时任务

server/
└─ config/
   └─ components/
      └─ celery.py                                               (M) 配置 Beat 定时任务
```

### 1.2 前端文件

```text
web/src/app/cmdb/
├─ api/
│  └─ subscription.ts                                            (A) 订阅规则 API 调用
├─ types/
│  └─ subscription.ts                                            (A) 订阅相关类型定义
├─ hooks/
│  └─ useSubscription.ts                                         (A) 订阅相关 Hooks
├─ components/
│  └─ subscription/
│     ├─ SubscriptionDrawer.tsx                                  (A) 规则管理抽屉（主入口）
│     ├─ SubscriptionRuleList.tsx                                (A) 规则列表组件
│     ├─ SubscriptionRuleForm.tsx                                (A) 规则创建/编辑表单
│     ├─ TriggerTypeConfig.tsx                                   (A) 触发类型配置区
│     ├─ InstanceSelector.tsx                                    (A) 实例选择器
│     └─ RecipientSelector.tsx                                   (A) 接收对象选择器
├─ (pages)/
│  └─ assetData/
│     ├─ list/
│     │  ├─ page.tsx                                             (M) 添加"数据订阅"按钮
│     │  └─ components/
│     │     └─ ActionBar.tsx                                     (M) 添加"订阅"按钮
│     └─ detail/
│        └─ page.tsx                                             (M) 添加"订阅"按钮
└─ locales/
   ├─ zh.json                                                    (M) 中文文案
   └─ en.json                                                    (M) 英文文案
```

---

## 2) 核心数据结构 / Schema 定义

### 2.1 Django Model

```python
# server/apps/cmdb/models/subscription_rule.py

from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class SubscriptionRule(MaintainerInfo, TimeInfo):
    """
    CMDB 数据订阅规则模型。
    
    支持三类触发类型（可多选）：
    - attribute_change: 属性变化
    - relation_change: 关联变化（一跳）
    - expiration: 临近到期
    """

    name = models.CharField(max_length=128, verbose_name="规则名称")
    organization = models.BigIntegerField(db_index=True, verbose_name="所属组织ID")
    model_id = models.CharField(max_length=100, db_index=True, verbose_name="目标模型ID")
    
    # 筛选类型：condition=过滤条件, instances=实例选择
    filter_type = models.CharField(
        max_length=20,
        choices=[("condition", "过滤条件"), ("instances", "实例选择")],
        default="instances",
        verbose_name="筛选类型"
    )
    # 实例筛选数据，结构见下方说明
    instance_filter = JSONField(default=dict, verbose_name="实例筛选数据")
    
    # 触发类型列表（多选）
    trigger_types = JSONField(default=list, verbose_name="触发类型列表")
    # 触发条件配置，按类型分别存储
    trigger_config = JSONField(default=dict, verbose_name="触发条件配置")
    
    # 接收对象：{"users": ["user1", "user2"], "groups": [1, 2]}
    recipients = JSONField(default=dict, verbose_name="接收对象")
    # 通知渠道 ID 列表（支持多选）
    channel_ids = JSONField(default=list, verbose_name="通知渠道ID列表")
    
    is_enabled = models.BooleanField(default=True, db_index=True, verbose_name="启用状态")
    # last_triggered_at 同时作为上次检查时间使用
    last_triggered_at = models.DateTimeField(null=True, blank=True, verbose_name="最近触发/检查时间")
    
    # 实例快照数据，用于关联变化检测
    snapshot_data = JSONField(default=dict, verbose_name="实例快照数据")

    class Meta:
        db_table = "cmdb_subscription_rule"
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uniq_sub_rule_name"),
        ]
        indexes = [
            models.Index(fields=["organization"], name="idx_sub_rule_org"),
            models.Index(fields=["model_id"], name="idx_sub_rule_model"),
            models.Index(fields=["is_enabled"], name="idx_sub_rule_enabled"),
        ]
        verbose_name = "订阅规则"
        verbose_name_plural = "订阅规则"

    def __str__(self):
        return f"SubscriptionRule({self.id}:{self.name})"
```

### 2.2 常量定义

```python
# server/apps/cmdb/constants/subscription.py

from enum import Enum


class FilterType(str, Enum):
    """筛选类型"""
    CONDITION = "condition"      # 过滤条件模式
    INSTANCES = "instances"      # 实例选择模式


class TriggerType(str, Enum):
    """触发类型"""
    ATTRIBUTE_CHANGE = "attribute_change"   # 属性变化
    RELATION_CHANGE = "relation_change"     # 关联变化（一跳）
    EXPIRATION = "expiration"               # 临近到期
    INSTANCE_ADDED = "instance_added"       # 实例新增（进入订阅范围）
    INSTANCE_DELETED = "instance_deleted"   # 实例删除（退出订阅范围）


# Redis Key 前缀与格式
SUBSCRIPTION_AGG_KEY_PREFIX = "cmdb:sub_agg"
# 完整 Key 格式: cmdb:sub_agg:{rule_id}:{trigger_type}:{window_minute}
# 示例: cmdb:sub_agg:123:attribute_change:202603181015

# 聚合窗口 TTL（秒）
SUBSCRIPTION_AGG_TTL = 120

# 检查周期（分钟）
SUBSCRIPTION_CHECK_INTERVAL = 2

# 通知内容展示的最大实例数
NOTIFICATION_MAX_DISPLAY_INSTANCES = 5
```

### 2.3 数据结构说明

#### `instance_filter` 结构

```python
# 当 filter_type = "condition"（过滤条件模式）
{
    "query_list": [
        {"field": "status", "type": "str=", "value": "running"},
        {"field": "organization", "type": "list[]", "value": [1, 2]}
    ]
}
# 复用现有 query_list 结构，最多 8 条件，AND 逻辑

# 当 filter_type = "instances"（实例选择模式）
{
    "instance_ids": [1, 2, 3, 4, 5]
}
# 直接存储用户选择的实例 ID 列表
```

#### `trigger_config` 结构

```python
{
    # 属性变化配置（当 trigger_types 包含 "attribute_change"）
    "attribute_change": {
        "fields": ["memory", "cpu", "status"]  # 监听的字段列表
    },
    
    # 关联变化配置（当 trigger_types 包含 "relation_change"）
    "relation_change": {
        "related_model": "disk",               # 关联模型 ID
        "fields": ["capacity", "status"]       # 监听的关联模型字段（可选）
    },
    
    # 临近到期配置（当 trigger_types 包含 "expiration"）
    "expiration": {
        "time_field": "warranty_end_date",     # 时间字段 ID
        "days_before": 30                       # 提前天数
    }
}
```

#### `snapshot_data` 结构

```python
{
    "instances": [1, 2, 3],                     # 上次检查的实例 ID 列表
    "relations": {
        "1": {"disk": [33, 44], "network": [55]},
        "2": {"disk": [33]},
        "3": {}
    }
}
```

#### `recipients` 结构

```python
{
    "users": ["admin", "user1", "user2"],      # 用户名列表
    "groups": [1, 2, 3]                         # 用户组 ID 列表
}
```

### 2.4 Serializer

```python
# server/apps/cmdb/serializers/subscription.py

from rest_framework import serializers
from apps.cmdb.models.subscription_rule import SubscriptionRule


class SubscriptionRuleSerializer(serializers.ModelSerializer):
    """订阅规则序列化器"""
    
    can_manage = serializers.SerializerMethodField(help_text="当前用户是否可管理此规则")
    
    class Meta:
        model = SubscriptionRule
        fields = [
            "id", "name", "organization", "model_id",
            "filter_type", "instance_filter",
            "trigger_types", "trigger_config",
            "recipients", "channel_ids",
            "is_enabled", "last_triggered_at",
            "created_by", "created_at", "updated_by", "updated_at",
            "can_manage"
        ]
        read_only_fields = [
            "id", "last_triggered_at", "snapshot_data",
            "created_by", "created_at", "updated_by", "updated_at",
            "can_manage"
        ]

    def get_can_manage(self, obj) -> bool:
        """判断当前用户是否可管理此规则（仅所属组织精确匹配时可管理）"""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return False
        current_team = getattr(request.user, "current_team", None)
        return obj.organization == current_team

    def validate_instance_filter(self, value):
        """校验实例筛选数据结构"""
        filter_type = self.initial_data.get("filter_type", "instances")
        if filter_type == "condition":
            query_list = value.get("query_list", [])
            if not isinstance(query_list, list):
                raise serializers.ValidationError("query_list 必须为列表")
            if len(query_list) > 8:
                raise serializers.ValidationError("筛选条件最多支持 8 个")
        elif filter_type == "instances":
            instance_ids = value.get("instance_ids", [])
            if not isinstance(instance_ids, list):
                raise serializers.ValidationError("instance_ids 必须为列表")
            if not instance_ids:
                raise serializers.ValidationError("至少选择一个实例")
        return value

    def validate_trigger_types(self, value):
        """校验触发类型"""
        valid_types = {"attribute_change", "relation_change", "expiration"}
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少选择一种触发类型")
        if not set(value).issubset(valid_types):
            raise serializers.ValidationError(f"触发类型必须为 {valid_types} 中的值")
        return value

    def validate_recipients(self, value):
        """校验接收对象"""
        users = value.get("users", [])
        groups = value.get("groups", [])
        if not users and not groups:
            raise serializers.ValidationError("至少选择一个接收对象")
        return value
```

### 2.5 前端 TypeScript 类型定义

```typescript
// web/src/app/cmdb/types/subscription.ts

/** 筛选类型 */
export type FilterType = 'condition' | 'instances';

/** 触发类型 */
export type TriggerType = 'attribute_change' | 'relation_change' | 'expiration';

/** 查询条件（复用现有类型） */
export interface QueryCondition {
  field: string;
  type: string;
  value: string | number | (string | number)[];
}

/** 过滤条件模式 */
export interface ConditionFilter {
  query_list: QueryCondition[];
}

/** 实例选择模式 */
export interface InstancesFilter {
  instance_ids: number[];
}

/** 属性变化配置 */
export interface AttributeChangeConfig {
  fields: string[];
}

/** 关联变化配置 */
export interface RelationChangeConfig {
  related_model: string;
  fields?: string[];
}

/** 临近到期配置 */
export interface ExpirationConfig {
  time_field: string;
  days_before: number;
}

/** 触发配置 */
export interface TriggerConfig {
  attribute_change?: AttributeChangeConfig;
  relation_change?: RelationChangeConfig;
  expiration?: ExpirationConfig;
}

/** 接收对象 */
export interface Recipients {
  users: string[];
  groups: number[];
}

/** 订阅规则完整类型（查询返回） */
export interface SubscriptionRule {
  id: number;
  name: string;
  organization: number;
  model_id: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  trigger_types: TriggerType[];
  trigger_config: TriggerConfig;
  recipients: Recipients;
  channel_ids: number[];
  is_enabled: boolean;
  last_triggered_at: string | null;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  can_manage: boolean;  // 只读，由后端计算
}

/** 创建订阅规则请求 */
export interface SubscriptionRuleCreate {
  name: string;
  organization: number;
  model_id: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  trigger_types: TriggerType[];
  trigger_config: TriggerConfig;
  recipients: Recipients;
  channel_ids: number[];
  is_enabled?: boolean;
}

/** 更新订阅规则请求 */
export type SubscriptionRuleUpdate = Partial<SubscriptionRuleCreate>;

/** 规则列表查询参数 */
export interface SubscriptionListParams {
  search?: string;
  page?: number;
  page_size?: number;
}

/** 快速订阅入口类型 */
export type QuickSubscribeSource = 
  | 'list_selection'   // 实例列表多选
  | 'list_filter'      // 实例列表筛选
  | 'detail'           // 实例详情页
  | 'drawer';          // 管理弹框新建

/** 快速订阅默认值配置 */
export interface QuickSubscribeDefaults {
  source: QuickSubscribeSource;
  model_id: string;
  model_name: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  name: string;
  organization: number;
  recipients: Recipients;
}
```

---

## 3) 核心函数 / 接口签名 (API & Signatures)

### 3.1 ViewSet

```python
# server/apps/cmdb/views/subscription.py

from typing import List
from django.db.models import QuerySet
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.serializers.subscription import SubscriptionRuleSerializer
from apps.core.decorators.uma_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    CMDB 数据订阅规则 ViewSet。
    
    提供订阅规则的 CRUD 操作，以及启停功能。
    权限控制：列表查询当前组织及子组织可见，管理操作仅当前组织可执行。
    """
    
    queryset = SubscriptionRule.objects.all().order_by("-created_at")
    serializer_class = SubscriptionRuleSerializer

    def get_queryset(self) -> QuerySet:
        """获取当前用户可见的订阅规则（当前组织及子组织）"""
        pass

    @HasPermission("subscription_rule-View")
    def list(self, request: Request, *args, **kwargs) -> Response:
        """查询订阅规则列表"""
        pass

    @HasPermission("subscription_rule-Add")
    def create(self, request: Request, *args, **kwargs) -> Response:
        """创建订阅规则"""
        pass

    @HasPermission("subscription_rule-Edit")
    def update(self, request: Request, *args, **kwargs) -> Response:
        """更新订阅规则"""
        pass

    @HasPermission("subscription_rule-Delete")
    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """删除订阅规则"""
        pass

    @action(methods=["post"], detail=True)
    @HasPermission("subscription_rule-Edit")
    def toggle(self, request: Request, pk: int = None) -> Response:
        """启停订阅规则"""
        pass

    def _check_manage_permission(self, rule: SubscriptionRule) -> bool:
        """检查当前用户是否有管理权限（规则所属组织与当前用户组织精确匹配）"""
        pass

    def _get_organization_with_children(self, org_id: int) -> List[int]:
        """获取组织及其所有子组织 ID 列表"""
        pass
```

### 3.2 触发检测服务

```python
# server/apps/cmdb/services/subscription_trigger.py

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Set

from apps.cmdb.models.subscription_rule import SubscriptionRule


@dataclass
class TriggerEvent:
    """触发事件数据结构"""
    rule_id: int
    rule_name: str
    model_id: str
    model_name: str
    trigger_type: str           # attribute_change / relation_change / expiration
    inst_id: int
    inst_name: str
    change_summary: str         # 变化摘要
    triggered_at: datetime


class SubscriptionTriggerService:
    """
    订阅触发检测服务。
    
    负责检测订阅规则的触发条件：属性变化、关联变化、临近到期。
    """
    
    def __init__(self, rule: SubscriptionRule):
        self.rule = rule
        self.events: List[TriggerEvent] = []
    
    def process(self) -> List[TriggerEvent]:
        """处理单条订阅规则的检测逻辑，返回触发事件列表"""
        pass

    def _get_current_instances(self) -> List[Dict[str, Any]]:
        """获取当前符合条件的实例列表（根据 filter_type 选择查询策略）"""
        pass

    def _get_relation_instances(self, instance_ids: List[int], related_model: str) -> Dict[int, List[int]]:
        """获取实例的一跳关联实例，返回 {源实例ID: [关联实例ID列表]}"""
        pass

    def _build_current_snapshot(self, instances: List[Dict], relations: Dict) -> Dict[str, Any]:
        """构建当前快照数据"""
        pass

    def _check_attribute_change(self, instances: List[Dict]) -> List[TriggerEvent]:
        """检测属性变化（基于 ChangeRecord 对比 before_data/after_data）"""
        pass

    def _check_relation_change(self, current_snapshot: Dict) -> List[TriggerEvent]:
        """检测关联变化（对比当前快照与上次快照）"""
        pass

    def _check_expiration(self, instances: List[Dict]) -> List[TriggerEvent]:
        """检测临近到期（检查时间字段是否在目标范围内）"""
        pass

    def _update_snapshot(self, current_snapshot: Dict) -> None:
        """更新规则的快照数据和检查时间"""
        pass

    @staticmethod
    def _get_changed_fields(before_data: Dict, after_data: Dict) -> Set[str]:
        """对比变更前后数据，返回变化的字段名集合"""
        pass
```

### 3.3 Celery Tasks

```python
# server/apps/cmdb/tasks/celery_tasks.py (新增部分)

import json
import logging
from datetime import datetime, timedelta
from typing import List, Any

from celery import shared_task
from django_redis import get_redis_connection

from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService, TriggerEvent
from apps.system_mgmt.nats_api import send_msg_with_channel

logger = logging.getLogger("celery")


@shared_task
def check_subscription_rules() -> None:
    """
    检查所有启用的订阅规则（每 2 分钟执行）。
    
    流程：查询启用规则 → 遍历检测 → 写入 Redis 聚合队列
    """
    pass


@shared_task
def send_subscription_notifications() -> None:
    """
    发送订阅通知（每分钟执行）。
    
    流程：扫描 Redis 聚合 Key → 按触发类型分组 → 构建通知内容 → 调用 send_msg_with_channel 发送
    
    关键逻辑：
    - Redis Key 格式: cmdb:sub_agg:{rule_id}:{trigger_type}:{window_minute}
    - 不同触发类型分别发送独立通知，不混合展示
    """
    pass


def _write_event_to_redis(event: TriggerEvent, trigger_type: str) -> None:
    """
    将触发事件写入 Redis 聚合队列。
    
    Key 格式: cmdb:sub_agg:{rule_id}:{trigger_type}:{window_minute}
    按触发类型分别聚合，确保不同类型的变化分开发送。
    """
    pass


def _build_notification_content(
    rule: SubscriptionRule,
    events: List[dict],
    trigger_type: str
) -> tuple[str, str]:
    """
    构建通知内容，返回 (标题, 正文)。
    
    标题规则：
    - 单实例: "{模型名} {实例标识} {触发类型描述}"
    - 多实例: "{模型名} {数量} 个实例{触发类型描述}"
    
    数量级处理规则：
    - 1 个: 展示完整变化摘要
    - 2-5 个: 逐条列出每个实例的简要摘要
    - 超过 5 个: 展示前 5 个 + "另有 N 个实例发生同类变化"
    """
    pass


def _build_title(model_name: str, events: List[dict], trigger_type: str) -> str:
    """
    构建通知标题，按触发类型和实例数量动态生成。
    
    标题规则表见 4.7 节详细实现。
    """
    pass


def _format_change_summary(event: dict, trigger_type: str) -> str:
    """
    格式化变化摘要，使用符号约定。
    
    符号约定：
    - 属性变化: 字段名: 旧值 -> 新值
    - 实例新增: + 实例标识（匹配条件摘要）
    - 实例删除: - 实例标识（删除前关键标识）
    - 关联对象新增/删除: +/- 关联对象
    - 临近到期: 字段名: 到期日期（剩余 N 天）
    """
    pass


def _truncate_value(value: Any, max_length: int = 50) -> str:
    """截断过长的值，保留关键信息"""
    pass


def _get_trigger_type_display(trigger_type: str) -> str:
    """获取触发类型的显示文案"""
    pass


def _get_model_name(model_id: str) -> str:
    """获取模型显示名称"""
    pass


def _get_receivers_from_recipients(recipients: dict) -> List[str]:
    """从接收对象配置解析实际接收人列表（展开用户组成员）"""
    pass
```

### 3.4 前端 API 函数签名

```typescript
// web/src/app/cmdb/api/subscription.ts

import request from '@/utils/request';
import type {
  SubscriptionRule,
  SubscriptionRuleCreate,
  SubscriptionRuleUpdate,
  SubscriptionListParams,
} from '../types/subscription';
import type { PageResult } from '@/types/common';

const BASE_URL = '/cmdb/api/subscription';

/**
 * 获取订阅规则列表
 * @param params - 查询参数（search, page, page_size）
 * @returns 分页规则列表
 */
export async function getSubscriptionRules(
  params?: SubscriptionListParams
): Promise<PageResult<SubscriptionRule>> {
  return request.get(BASE_URL, { params });
}

/**
 * 获取单条订阅规则详情
 * @param id - 规则 ID
 * @returns 规则详情
 */
export async function getSubscriptionRule(id: number): Promise<SubscriptionRule> {
  return request.get(`${BASE_URL}/${id}/`);
}

/**
 * 创建订阅规则
 * @param data - 创建数据
 * @returns 新创建的规则
 */
export async function createSubscriptionRule(
  data: SubscriptionRuleCreate
): Promise<SubscriptionRule> {
  return request.post(BASE_URL + '/', data);
}

/**
 * 更新订阅规则
 * @param id - 规则 ID
 * @param data - 更新数据
 * @returns 更新后的规则
 */
export async function updateSubscriptionRule(
  id: number,
  data: SubscriptionRuleUpdate
): Promise<SubscriptionRule> {
  return request.patch(`${BASE_URL}/${id}/`, data);
}

/**
 * 删除订阅规则
 * @param id - 规则 ID
 */
export async function deleteSubscriptionRule(id: number): Promise<void> {
  return request.delete(`${BASE_URL}/${id}/`);
}

/**
 * 启停订阅规则
 * @param id - 规则 ID
 * @returns 更新后的规则
 */
export async function toggleSubscriptionRule(id: number): Promise<SubscriptionRule> {
  return request.post(`${BASE_URL}/${id}/toggle/`);
}
```

### 3.5 前端 Hooks 签名

```typescript
// web/src/app/cmdb/hooks/useSubscription.ts

import { useState, useCallback, useMemo } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import type {
  SubscriptionRule,
  SubscriptionRuleCreate,
  SubscriptionRuleUpdate,
  SubscriptionListParams,
  QuickSubscribeDefaults,
  QuickSubscribeSource,
  FilterType,
} from '../types/subscription';

/**
 * 订阅规则列表 Hook
 */
export function useSubscriptionList() {
  // 状态
  const [rules, setRules] = useState<SubscriptionRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  
  // 查询规则列表
  const fetchRules: (params?: SubscriptionListParams) => Promise<void>;
  
  // 刷新列表
  const refresh: () => Promise<void>;
  
  return { rules, loading, pagination, fetchRules, refresh };
}

/**
 * 订阅规则增删改 Hook
 */
export function useSubscriptionMutation() {
  const [submitting, setSubmitting] = useState(false);
  
  // 创建规则
  const createRule: (data: SubscriptionRuleCreate) => Promise<SubscriptionRule>;
  
  // 更新规则
  const updateRule: (id: number, data: SubscriptionRuleUpdate) => Promise<SubscriptionRule>;
  
  // 删除规则
  const deleteRule: (id: number) => Promise<void>;
  
  // 启停规则
  const toggleRule: (id: number) => Promise<SubscriptionRule>;
  
  return { submitting, createRule, updateRule, deleteRule, toggleRule };
}

/**
 * 快速订阅默认值生成 Hook
 * @param source - 入口来源
 * @param context - 上下文信息
 */
export function useQuickSubscribeDefaults(
  source: QuickSubscribeSource,
  context: {
    model_id: string;
    model_name: string;
    selectedInstanceIds?: number[];
    queryList?: any[];
    currentInstanceId?: number;
    currentInstanceName?: string;
    currentUser: string;
    currentOrganization: number;
  }
): QuickSubscribeDefaults {
  return useMemo(() => {
    const timestamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
    
    switch (source) {
      case 'list_selection':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: { instance_ids: context.selectedInstanceIds || [] },
          name: `${context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser], groups: [] },
        };
      case 'list_filter':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'condition' as FilterType,
          instance_filter: { query_list: context.queryList || [] },
          name: `${context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser], groups: [] },
        };
      case 'detail':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: { instance_ids: context.currentInstanceId ? [context.currentInstanceId] : [] },
          name: `${context.currentInstanceName || context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser], groups: [] },
        };
      default: // drawer
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: { instance_ids: [] },
          name: '',
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser], groups: [] },
        };
    }
  }, [source, context]);
}
```

---

## 4) 核心逻辑伪代码 (Step-by-Step Logic)

### 4.1 定时任务：check_subscription_rules

```python
@shared_task
def check_subscription_rules() -> None:
    logger.info("[Subscription] 开始检查订阅规则")
    
    # Step 1: 查询所有启用的订阅规则
    rules = SubscriptionRule.objects.filter(is_enabled=True)
    logger.info(f"[Subscription] 共 {rules.count()} 条启用规则")
    
    # Step 2: 遍历每条规则
    for rule in rules:
        try:
            logger.info(f"[Subscription] 处理规则 rule_id={rule.id}, name={rule.name}")
            
            # Step 3: 调用触发检测服务
            service = SubscriptionTriggerService(rule)
            events = service.process()
            
            # Step 4: 将触发事件写入 Redis 聚合队列
            for event in events:
                _write_event_to_redis(event)
                logger.info(f"[Subscription] 检测到触发事件 rule_id={rule.id}, trigger_type={event.trigger_type}")
                
        except Exception as e:
            logger.error(f"[Subscription] 处理规则失败 rule_id={rule.id}, error={str(e)}", exc_info=True)
    
    logger.info("[Subscription] 订阅规则检查完成")
```

### 4.2 触发检测服务：process

```python
def process(self) -> List[TriggerEvent]:
    events: List[TriggerEvent] = []
    
    # Step 1: 获取当前符合条件的实例列表
    if self.rule.filter_type == "condition":
        query_list = self.rule.instance_filter.get("query_list", [])
        instances = self._query_instances_by_condition(query_list)
    else:
        instance_ids = self.rule.instance_filter.get("instance_ids", [])
        instances = self._query_instances_by_ids(instance_ids)
    
    if not instances:
        return events
    
    instance_ids = [inst["inst_id"] for inst in instances]
    
    # Step 2: 如果包含 relation_change，查询关联实例
    relations = {}
    if "relation_change" in self.rule.trigger_types:
        related_model = self.rule.trigger_config.get("relation_change", {}).get("related_model")
        if related_model:
            relations = self._get_relation_instances(instance_ids, related_model)
    
    # Step 3: 构建当前快照
    current_snapshot = self._build_current_snapshot(instances, relations)
    
    # Step 4: 检测各类变化
    if "attribute_change" in self.rule.trigger_types:
        events.extend(self._check_attribute_change(instances))
    if "relation_change" in self.rule.trigger_types:
        events.extend(self._check_relation_change(current_snapshot))
    if "expiration" in self.rule.trigger_types:
        events.extend(self._check_expiration(instances))
    
    # Step 5: 更新快照和检查时间
    self._update_snapshot(current_snapshot)
    
    return events
```

### 4.3 属性变化检测

```python
def _check_attribute_change(self, instances: List[Dict]) -> List[TriggerEvent]:
    events = []
    
    # Step 1: 获取监听字段配置
    config = self.rule.trigger_config.get("attribute_change", {})
    watch_fields = set(config.get("fields", []))
    if not watch_fields:
        return events
    
    # Step 2: 查询 ChangeRecord（last_triggered_at 之后的 UPDATE_INST）
    instance_ids = [inst["inst_id"] for inst in instances]
    last_check = self.rule.last_triggered_at or datetime.min
    
    change_records = ChangeRecord.objects.filter(
        model_id=self.rule.model_id,
        type="UPDATE_INST",
        inst_id__in=instance_ids,
        created_at__gt=last_check
    )
    
    # Step 3: 遍历变更记录，检测变化字段
    for record in change_records:
        changed_fields = self._get_changed_fields(record.before_data, record.after_data)
        matched_fields = changed_fields & watch_fields
        
        if matched_fields:
            events.append(TriggerEvent(...))
    
    return events
```

### 4.4 关联变化检测

```python
def _check_relation_change(self, current_snapshot: Dict) -> List[TriggerEvent]:
    events = []
    
    # Step 1: 获取上次快照
    previous_relations = self.rule.snapshot_data.get("relations", {})
    current_relations = current_snapshot.get("relations", {})
    related_model = self.rule.trigger_config.get("relation_change", {}).get("related_model", "")
    
    # Step 2: 遍历实例，对比关联变化
    all_instance_ids = set(previous_relations.keys()) | set(current_relations.keys())
    
    for inst_id_str in all_instance_ids:
        prev_related = set(previous_relations.get(inst_id_str, {}).get(related_model, []))
        curr_related = set(current_relations.get(inst_id_str, {}).get(related_model, []))
        
        added = curr_related - prev_related      # 新增关联
        removed = prev_related - curr_related    # 删除关联
        
        if added or removed:
            events.append(TriggerEvent(...))
    
    return events
```

### 4.5 临近到期检测

```python
def _check_expiration(self, instances: List[Dict]) -> List[TriggerEvent]:
    events = []
    
    config = self.rule.trigger_config.get("expiration", {})
    time_field = config.get("time_field", "")
    days_before = config.get("days_before", 0)
    
    if not time_field or days_before <= 0:
        return events
    
    today = datetime.now().date()
    target_date = today + timedelta(days=days_before)
    
    for inst in instances:
        field_value = inst.get(time_field)
        expire_date = parse_date(field_value)
        
        if today <= expire_date <= target_date:
            days_remaining = (expire_date - today).days
            events.append(TriggerEvent(
                change_summary=f"字段 {time_field} 将在 {days_remaining} 天后到期（{expire_date}）",
                ...
            ))
    
    return events
```

### 4.6 通知发送

```python
@shared_task
def send_subscription_notifications() -> None:
    """
    发送订阅通知（每分钟执行）。
    
    流程：扫描 Redis 聚合 Key → 按触发类型分组 → 构建通知内容 → 调用 send_msg_with_channel 发送
    """
    logger.info("[Subscription] 开始发送订阅通知")
    
    redis_conn = get_redis_connection("default")
    
    # Step 1: 计算上一分钟的窗口时间
    now = datetime.now()
    prev_minute = (now - timedelta(minutes=1)).strftime("%Y%m%d%H%M")
    
    # Step 2: 扫描 Redis Key（按触发类型分别聚合）
    # Key 格式: cmdb:sub_agg:{rule_id}:{trigger_type}:{window_minute}
    pattern = f"cmdb:sub_agg:*:*:{prev_minute}"
    keys = redis_conn.keys(pattern)
    logger.info(f"[Subscription] 扫描到 {len(keys)} 个聚合 Key")
    
    # Step 3: 按规则+触发类型分组处理
    rule_type_events = {}  # {(rule_id, trigger_type): [events]}
    for key in keys:
        parts = key.decode().split(":")
        rule_id = int(parts[2])
        trigger_type = parts[3]
        events_data = redis_conn.smembers(key)
        
        key_tuple = (rule_id, trigger_type)
        if key_tuple not in rule_type_events:
            rule_type_events[key_tuple] = []
        rule_type_events[key_tuple].extend([json.loads(e) for e in events_data])
        redis_conn.delete(key)
    
    # Step 4: 按规则+触发类型分别发送通知（不同类型不混合）
    for (rule_id, trigger_type), events in rule_type_events.items():
        try:
            rule = SubscriptionRule.objects.get(id=rule_id)
            title, content = _build_notification_content(rule, events, trigger_type)
            receivers = _get_receivers_from_recipients(rule.recipients)
            
            # 遍历所有通知渠道发送
            for channel_id in rule.channel_ids:
                send_msg_with_channel(
                    channel_id=channel_id,
                    title=title,
                    content=content,
                    receivers=receivers
                )
            
            # 更新最近触发时间
            rule.last_triggered_at = now
            rule.save(update_fields=["last_triggered_at"])
            
            logger.info(f"[Subscription] 通知发送成功 rule_id={rule_id}, trigger_type={trigger_type}, events_count={len(events)}")
        except Exception as e:
            logger.error(f"[Subscription] 通知发送失败 rule_id={rule_id}, error={str(e)}", exc_info=True)
    
    logger.info("[Subscription] 订阅通知发送完成")
```

### 4.7 通知消息构建

```python
def _build_notification_content(
    rule: SubscriptionRule,
    events: List[dict],
    trigger_type: str
) -> tuple[str, str]:
    """
    构建通知内容，返回 (标题, 正文)。
    
    Args:
        rule: 订阅规则
        events: 触发事件列表
        trigger_type: 触发类型（attribute_change/relation_change/expiration/instance_added/instance_deleted）
    
    Returns:
        tuple[str, str]: (标题, 正文)
    
    标题规则：
    - 单实例: "{模型名} {实例标识} {触发类型描述}"
    - 多实例: "{模型名} {数量} 个实例{触发类型描述}"
    
    数量级处理规则：
    - 1 个: 展示完整变化摘要
    - 2-5 个: 逐条列出每个实例的简要摘要
    - 超过 5 个: 展示前 5 个 + "另有 N 个实例发生同类变化"
    """
    model_name = _get_model_name(rule.model_id)
    event_count = len(events)
    
    # Step 1: 构建标题
    title = _build_title(model_name, events, trigger_type)
    
    # Step 2: 构建正文
    content_lines = []
    content_lines.append(f"模型：{model_name}")
    
    if event_count == 1:
        # 单实例：展示完整摘要
        event = events[0]
        content_lines.append(f"实例：{event['inst_name']}")
        content_lines.append(f"触发类型：{_get_trigger_type_display(trigger_type)}")
        
        # 根据触发类型选择摘要标签
        if trigger_type == "expiration":
            content_lines.append(f"到期信息：{_format_change_summary(event, trigger_type)}")
        else:
            content_lines.append(f"变化摘要：{_format_change_summary(event, trigger_type)}")
        
        content_lines.append(f"触发时间：{event['triggered_at']}")
    else:
        # 多实例
        content_lines.append(f"触发类型：{_get_trigger_type_display(trigger_type)}")
        content_lines.append("变化摘要：")
        
        # 展示前 5 个
        display_events = events[:5]
        for i, event in enumerate(display_events, 1):
            summary = _format_change_summary(event, trigger_type)
            content_lines.append(f"{i}）{event['inst_name']}：{summary}")
        
        # 超过 5 个时添加汇总说明
        if event_count > 5:
            remaining = event_count - 5
            content_lines.append(f"另有 {remaining} 个实例发生同类变化")
        
        # 触发时间范围
        times = sorted([e['triggered_at'] for e in events])
        min_time, max_time = times[0], times[-1]
        if min_time == max_time:
            content_lines.append(f"触发时间：{min_time}")
        else:
            content_lines.append(f"触发时间范围：{min_time} 至 {max_time}")
    
    content = "\n".join(content_lines)
    logger.debug(f"[Subscription] 构建通知内容 title={title}, events_count={event_count}")
    return title, content


def _build_title(model_name: str, events: List[dict], trigger_type: str) -> str:
    """
    构建通知标题。
    
    标题规则表：
    | 触发类型 | 单实例标题 | 多实例标题 |
    |----------|------------|------------|
    | attribute_change | {模型名} {实例标识} 属性变化 | {模型名} {数量} 个实例属性变化 |
    | relation_change | {模型名} {实例标识} 关联对象变化 | {模型名} {数量} 个实例关联对象变化 |
    | expiration | {模型名} {实例标识} 临近到期提醒 | {模型名} {数量} 个实例临近到期提醒 |
    | instance_added | {模型名} 出现新增实例 | {模型名} {数量} 个新增实例 |
    | instance_deleted | {模型名} {实例标识} 已删除 | {模型名} {数量} 个实例已删除 |
    """
    event_count = len(events)
    
    type_display_map = {
        "attribute_change": ("属性变化", "个实例属性变化"),
        "relation_change": ("关联对象变化", "个实例关联对象变化"),
        "expiration": ("临近到期提醒", "个实例临近到期提醒"),
        "instance_added": ("出现新增实例", "个新增实例"),
        "instance_deleted": ("已删除", "个实例已删除"),
    }
    
    single_suffix, multi_suffix = type_display_map.get(trigger_type, ("变化", "个实例变化"))
    
    if event_count == 1:
        inst_name = events[0]['inst_name']
        if trigger_type == "instance_added":
            return f"{model_name} {single_suffix}"
        return f"{model_name} {inst_name} {single_suffix}"
    else:
        return f"{model_name} {event_count} {multi_suffix}"


def _format_change_summary(event: dict, trigger_type: str) -> str:
    """
    格式化变化摘要，使用符号约定。
    
    符号约定表：
    | 变化类型 | 符号表达 |
    |----------|----------|
    | 属性变化 | 字段名: 旧值 -> 新值 |
    | 实例新增 | + 实例标识（匹配条件摘要） |
    | 实例删除 | - 实例标识（删除前关键标识） |
    | 关联对象新增 | + 关联对象 |
    | 关联对象删除 | - 关联对象 |
    | 关联对象属性变化 | 关联字段: 旧值 -> 新值 |
    | 临近到期 | 字段名: 到期日期（剩余 N 天） |
    """
    if trigger_type == 'attribute_change':
        # 属性变化：字段名: 旧值 -> 新值
        changes = event.get('changes', [])
        if changes:
            summaries = []
            for change in changes:
                field_name = change.get('field_name', change.get('field', ''))
                old_value = _truncate_value(change.get('old_value', ''))
                new_value = _truncate_value(change.get('new_value', ''))
                summaries.append(f"{field_name}: {old_value} -> {new_value}")
            return "，".join(summaries)
        return event.get('change_summary', '')
    
    elif trigger_type == 'instance_added':
        # 实例新增：+ 实例标识（匹配条件摘要）
        inst_name = event.get('inst_name', '')
        match_info = event.get('match_info', '')
        return f"+ {inst_name}（{match_info}）" if match_info else f"+ {inst_name}"
    
    elif trigger_type == 'instance_deleted':
        # 实例删除：- 实例标识（删除前关键标识）
        inst_name = event.get('inst_name', '')
        key_info = event.get('key_info', '')
        return f"- {inst_name}（{key_info}）" if key_info else f"- {inst_name}"
    
    elif trigger_type == 'relation_change':
        # 关联变化：+ 关联对象 / - 关联对象 / 关联字段: 旧值 -> 新值
        relation_type = event.get('relation_type', 'updated')  # added/deleted/updated
        related_name = event.get('related_inst_name', '')
        if relation_type == 'added':
            return f"+ {related_name}"
        elif relation_type == 'deleted':
            return f"- {related_name}"
        else:
            # 关联对象属性变化
            changes = event.get('changes', [])
            if changes:
                summaries = []
                for change in changes:
                    field_name = change.get('field_name', change.get('field', ''))
                    old_value = _truncate_value(change.get('old_value', ''))
                    new_value = _truncate_value(change.get('new_value', ''))
                    summaries.append(f"{related_name} {field_name}: {old_value} -> {new_value}")
                return "，".join(summaries)
            return f"{related_name} 属性更新"
    
    elif trigger_type == 'expiration':
        # 临近到期：字段名: 到期日期（剩余 N 天）
        field_name = event.get('time_field_name', event.get('time_field', ''))
        expire_date = event.get('expire_date', '')
        days_remaining = event.get('days_remaining', 0)
        return f"{field_name}: {expire_date}（剩余 {days_remaining} 天）"
    
    # 默认返回原始摘要
    return event.get('change_summary', '')


def _truncate_value(value: Any, max_length: int = 50) -> str:
    """
    截断过长的值，保留关键信息。
    
    Args:
        value: 原始值
        max_length: 最大长度，默认 50
    
    Returns:
        str: 截断后的字符串
    """
    str_value = str(value) if value is not None else ''
    if len(str_value) > max_length:
        return str_value[:max_length - 3] + "..."
    return str_value


def _get_trigger_type_display(trigger_type: str) -> str:
    """获取触发类型的显示文案"""
    display_map = {
        "attribute_change": "属性变化",
        "relation_change": "关联变化",
        "expiration": "临近到期",
        "instance_added": "实例新增",
        "instance_deleted": "实例删除",
    }
    return display_map.get(trigger_type, trigger_type)


def _get_model_name(model_id: str) -> str:
    """获取模型显示名称"""
    from apps.cmdb.services.model import ModelManage
    model_info = ModelManage.search_model_info(model_id)
    return model_info.get('model_name', model_id) if model_info else model_id


def _get_receivers_from_recipients(recipients: dict) -> List[str]:
    """
    从接收对象配置解析实际接收人列表。
    
    Args:
        recipients: {"users": ["user1", "user2"], "groups": [1, 2]}
    
    Returns:
        List[str]: 用户名列表
    """
    receivers = []
    
    # 添加直接用户
    users = recipients.get("users", [])
    receivers.extend(users)
    
    # 展开用户组成员
    groups = recipients.get("groups", [])
    if groups:
        from apps.system_mgmt.models import Group
        group_users = Group.objects.filter(id__in=groups).values_list("users__username", flat=True)
        receivers.extend([u for u in group_users if u])
    
    # 去重并返回
    return list(set(receivers))
```

---

## 5) Celery Beat 配置

```python
# server/config/components/celery.py (新增部分)

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # 订阅规则检查（每 2 分钟）
    "check-subscription-rules": {
        "task": "apps.cmdb.tasks.celery_tasks.check_subscription_rules",
        "schedule": crontab(minute="*/2"),
    },
    # 订阅通知发送（每分钟）
    "send-subscription-notifications": {
        "task": "apps.cmdb.tasks.celery_tasks.send_subscription_notifications",
        "schedule": crontab(minute="*"),
    },
}
```

---

## 6) 前端组件规格 (Component Specifications)

### 6.1 规则管理抽屉（SubscriptionDrawer）

```typescript
// web/src/app/cmdb/components/subscription/SubscriptionDrawer.tsx

interface SubscriptionDrawerProps {
  /** 是否显示 */
  open: boolean;
  /** 关闭回调 */
  onClose: () => void;
  /** 当前模型 ID */
  modelId: string;
  /** 当前模型名称 */
  modelName: string;
  /** 快速订阅默认值（来自四个入口） */
  quickDefaults?: QuickSubscribeDefaults;
}

/**
 * 规则管理抽屉组件
 * 
 * 功能：
 * - 展示当前模型的订阅规则列表（包含子组织规则）
 * - 新建规则按钮 → 打开 SubscriptionRuleForm
 * - 搜索框按规则名称过滤
 * - 接收 quickDefaults 时自动打开新建表单并填充默认值
 * 
 * 布局：
 * - 宽度 720px
 * - 标题栏："数据订阅规则" + 关闭按钮
 * - 工具栏：新建按钮 + 搜索框
 * - 内容区：SubscriptionRuleList
 */
export const SubscriptionDrawer: React.FC<SubscriptionDrawerProps>;
```

### 6.2 规则列表组件（SubscriptionRuleList）

```typescript
// web/src/app/cmdb/components/subscription/SubscriptionRuleList.tsx

interface SubscriptionRuleListProps {
  /** 规则列表数据 */
  rules: SubscriptionRule[];
  /** 加载状态 */
  loading: boolean;
  /** 分页配置 */
  pagination: { current: number; pageSize: number; total: number };
  /** 分页变化回调 */
  onPageChange: (page: number, pageSize: number) => void;
  /** 查看/编辑规则 */
  onEdit: (rule: SubscriptionRule) => void;
  /** 删除规则 */
  onDelete: (id: number) => void;
  /** 启停规则 */
  onToggle: (id: number) => void;
}

/**
 * 规则列表组件
 * 
 * 表格列：
 * | 规则名称 | 所属组织 | 目标模型 | 状态 | 最近触发时间 | 操作 |
 * 
 * 权限态处理：
 * - can_manage=true: 操作按钮正常显示
 * - can_manage=false: 操作按钮置灰，hover 显示"仅限所属组织管理"
 * 
 * 状态列：
 * - is_enabled=true: 绿色开关 + "启用"
 * - is_enabled=false: 灰色开关 + "停用"
 */
export const SubscriptionRuleList: React.FC<SubscriptionRuleListProps>;
```

### 6.3 规则表单组件（SubscriptionRuleForm）

```typescript
// web/src/app/cmdb/components/subscription/SubscriptionRuleForm.tsx

interface SubscriptionRuleFormProps {
  /** 编辑模式时的规则数据 */
  initialValues?: SubscriptionRule;
  /** 快速订阅默认值 */
  quickDefaults?: QuickSubscribeDefaults;
  /** 当前模型 ID */
  modelId: string;
  /** 当前模型名称 */
  modelName: string;
  /** 提交中状态 */
  submitting: boolean;
  /** 提交回调（保存并启用） */
  onSubmitAndEnable: (data: SubscriptionRuleCreate) => Promise<void>;
  /** 提交回调（仅保存） */
  onSubmitOnly: (data: SubscriptionRuleCreate) => Promise<void>;
  /** 取消回调 */
  onCancel: () => void;
}

/**
 * 规则创建/编辑表单
 * 
 * 表单字段：
 * - 规则名称: Input, maxLength=128, required
 * - 所属组织: Select, disabled（默认当前组织）
 * - 目标模型: Select, disabled（由入口决定）
 * - 筛选类型: Radio（过滤条件/实例选择）
 * - 选择实例: InstanceSelector
 * - 触发类型: TriggerTypeConfig（多选卡片）
 * - 接收对象: RecipientSelector
 * - 通知渠道: Select multiple, required
 * 
 * 按钮组：
 * - "保存并启用": 提交 is_enabled=true
 * - "仅保存": 提交 is_enabled=false
 * - "取消": 关闭表单
 */
export const SubscriptionRuleForm: React.FC<SubscriptionRuleFormProps>;
```

### 6.4 触发类型配置区（TriggerTypeConfig）

```typescript
// web/src/app/cmdb/components/subscription/TriggerTypeConfig.tsx

interface TriggerTypeConfigProps {
  /** 当前选中的触发类型列表 */
  value: TriggerType[];
  /** 变化回调 */
  onChange: (types: TriggerType[], config: TriggerConfig) => void;
  /** 当前模型的属性列表 */
  modelFields: { id: string; name: string; type: string }[];
  /** 当前模型的关联模型列表 */
  relatedModels: { id: string; name: string }[];
  /** 当前模型的日期类型字段列表 */
  dateFields: { id: string; name: string }[];
  /** 当前触发配置 */
  triggerConfig: TriggerConfig;
}

/**
 * 触发类型配置组件
 * 
 * 三种卡片布局（水平排列，多选）：
 * 
 * [属性变化]
 * - 描述："监听指定字段的值变化"
 * - 选中后展开：字段多选组件
 * 
 * [关联变化]
 * - 描述："监听关联实例的新增或删除"
 * - 选中后展开：关联模型下拉 + 关联字段多选（可选）
 * 
 * [临近到期]
 * - 描述："监听时间字段临近到期"
 * - 选中后展开：时间字段下拉 + 提前天数输入框（标注"自然日"）
 */
export const TriggerTypeConfig: React.FC<TriggerTypeConfigProps>;
```

### 6.5 实例选择器（InstanceSelector）

```typescript
// web/src/app/cmdb/components/subscription/InstanceSelector.tsx

interface InstanceSelectorProps {
  /** 筛选类型 */
  filterType: FilterType;
  /** 当前值 */
  value: ConditionFilter | InstancesFilter;
  /** 变化回调 */
  onChange: (value: ConditionFilter | InstancesFilter) => void;
  /** 当前模型 ID */
  modelId: string;
  /** 当前模型的属性列表 */
  modelFields: { id: string; name: string; type: string }[];
}

/**
 * 实例选择器组件
 * 
 * 根据 filterType 切换不同 UI：
 * 
 * filterType="condition"（过滤条件模式）：
 * - 显示条件构建器（复用现有 FilterBuilder）
 * - 最多 8 个条件，展示"最多8个条件"提示
 * - 条件之间展示"且（AND）"标签
 * 
 * filterType="instances"（实例选择模式）：
 * - 显示实例列表表格（带复选框）
 * - 支持搜索与分页
 * - 已选实例以 Tag 形式展示在顶部
 */
export const InstanceSelector: React.FC<InstanceSelectorProps>;
```

### 6.6 接收对象选择器（RecipientSelector）

```typescript
// web/src/app/cmdb/components/subscription/RecipientSelector.tsx

interface RecipientSelectorProps {
  /** 当前值 */
  value: Recipients;
  /** 变化回调 */
  onChange: (value: Recipients) => void;
}

/**
 * 接收对象选择器组件
 * 
 * 布局：
 * - 用户选择区：多选下拉，数据源为系统用户列表
 * - 用户组选择区：多选下拉，数据源为用户组列表
 * 
 * 校验：
 * - 至少选择一个用户或一个用户组
 */
export const RecipientSelector: React.FC<RecipientSelectorProps>;
```

### 6.7 四个快速订阅入口集成

#### 实例列表页多选入口

```typescript
// web/src/app/cmdb/(pages)/assetData/list/components/ActionBar.tsx (修改)

// 在 ActionBar 组件中添加"订阅"按钮
// 条件：selectedRowKeys.length > 0 时显示

<Button
  onClick={() => {
    onOpenSubscription({
      source: 'list_selection',
      selectedInstanceIds: selectedRowKeys,
    });
  }}
>
  {t('subscription.subscribe')}
</Button>
```

#### 实例列表页筛选入口

```typescript
// web/src/app/cmdb/(pages)/assetData/list/page.tsx (修改)

// 在筛选条件存在时，显示"按此条件订阅"按钮
// 条件：queryList.length > 0 && selectedRowKeys.length === 0

<Button
  onClick={() => {
    onOpenSubscription({
      source: 'list_filter',
      queryList: currentQueryList,
    });
  }}
>
  {t('subscription.subscribeByFilter')}
</Button>
```

#### 实例详情页入口

```typescript
// web/src/app/cmdb/(pages)/assetData/detail/page.tsx (修改)

// 在详情页操作区添加"订阅"按钮

<Button
  onClick={() => {
    onOpenSubscription({
      source: 'detail',
      currentInstanceId: instance.inst_id,
      currentInstanceName: instance.inst_name,
    });
  }}
>
  {t('subscription.subscribe')}
</Button>
```

#### 管理弹框入口（资产页"数据订阅"按钮）

```typescript
// web/src/app/cmdb/(pages)/assetData/list/page.tsx (修改)

// 在页面右上角添加"数据订阅"按钮

<Button
  icon={<BellOutlined />}
  onClick={() => setSubscriptionDrawerOpen(true)}
>
  {t('subscription.dataSubscription')}
</Button>

<SubscriptionDrawer
  open={subscriptionDrawerOpen}
  onClose={() => setSubscriptionDrawerOpen(false)}
  modelId={currentModelId}
  modelName={currentModelName}
/>
```

---

## 7) 第三方依赖与环境要求

**无新增依赖**

复用现有依赖：
- `django-redis`：Redis 连接（聚合窗口）
- `celery`：定时任务
- `apps.system_mgmt.nats_api`：通知发送
- `apps.cmdb.graph`：FalkorDB 图数据库查询

---

## 8) URL 路由配置

```python
# server/apps/cmdb/urls.py (新增部分)

from rest_framework.routers import DefaultRouter
from apps.cmdb.views.subscription import SubscriptionViewSet

router = DefaultRouter()
router.register(r"subscription", SubscriptionViewSet, basename="subscription")

urlpatterns = [
    # ... 现有路由 ...
] + router.urls
```

---

## 9) 测试方案

### 9.1 后端单元测试

```python
# server/apps/cmdb/tests/test_subscription.py

class TestSubscriptionRule:
    """订阅规则模型测试"""
    
    def test_create_rule_with_condition_filter(self):
        """测试创建过滤条件模式的规则"""
        pass
    
    def test_create_rule_with_instances_filter(self):
        """测试创建实例选择模式的规则"""
        pass
    
    def test_validate_instance_filter_max_conditions(self):
        """测试筛选条件最多 8 个"""
        pass


class TestSubscriptionTriggerService:
    """触发检测服务测试"""
    
    def test_check_attribute_change(self):
        """测试属性变化检测"""
        pass
    
    def test_check_relation_change_added(self):
        """测试关联新增检测"""
        pass
    
    def test_check_relation_change_removed(self):
        """测试关联删除检测"""
        pass
    
    def test_check_expiration(self):
        """测试临近到期检测"""
        pass
```

### 9.2 后端集成测试

```python
class TestSubscriptionIntegration:
    """订阅功能集成测试"""
    
    def test_full_flow_attribute_change(self):
        """完整流程：创建规则 → 修改实例 → 检测触发 → 发送通知"""
        pass
    
    def test_aggregation_window(self):
        """测试 1 分钟聚合窗口"""
        pass
    
    def test_organization_permission(self):
        """测试组织权限控制"""
        pass
```

### 9.3 前端组件测试

```typescript
// web/src/app/cmdb/components/subscription/__tests__/

describe('SubscriptionRuleForm', () => {
  it('应正确渲染表单字段', () => {});
  it('应校验规则名称必填', () => {});
  it('应校验至少选择一种触发类型', () => {});
  it('应校验至少选择一个接收对象', () => {});
  it('应正确处理快速订阅默认值填充', () => {});
});

describe('TriggerTypeConfig', () => {
  it('应支持多选触发类型', () => {});
  it('选中属性变化时应展开字段选择', () => {});
  it('选中关联变化时应展开关联模型选择', () => {});
  it('选中临近到期时应展开时间配置', () => {});
});

describe('InstanceSelector', () => {
  it('condition 模式应渲染条件构建器', () => {});
  it('instances 模式应渲染实例表格', () => {});
  it('应限制条件最多 8 个', () => {});
});

describe('useQuickSubscribeDefaults', () => {
  it('list_selection 入口应返回正确默认值', () => {});
  it('list_filter 入口应返回正确默认值', () => {});
  it('detail 入口应返回正确默认值', () => {});
  it('drawer 入口应返回空默认值', () => {});
});
```

---

## 10) 发布与回滚策略

### 发布步骤

1. **数据库迁移**：`python manage.py makemigrations cmdb && python manage.py migrate`
2. **Celery Worker 重启**：确保新任务加载
3. **Celery Beat 重启**：确保定时任务调度生效

### 回滚策略

1. **代码回滚**：`git revert <commit>`
2. **数据库回滚**：`python manage.py migrate cmdb <previous_migration>`
3. **Celery 配置回滚**：移除 CELERY_BEAT_SCHEDULE 中的新增配置

---

## 11) 关键日志点

| 位置 | 级别 | 内容 |
|------|-----|------|
| check_subscription_rules 开始 | INFO | `[Subscription] 开始检查订阅规则` |
| check_subscription_rules 规则数 | INFO | `[Subscription] 共 {count} 条启用规则` |
| 处理单条规则 | INFO | `[Subscription] 处理规则 rule_id={id}, name={name}` |
| 检测到事件 | INFO | `[Subscription] 检测到触发事件 rule_id={id}, trigger_type={type}` |
| 处理失败 | ERROR | `[Subscription] 处理规则失败 rule_id={id}, error={error}` |
| 通知发送成功 | INFO | `[Subscription] 通知发送成功 rule_id={id}, events_count={count}` |
| 通知发送失败 | ERROR | `[Subscription] 通知发送失败 rule_id={id}, error={error}` |

---

## 12) 国际化配置 (i18n)

### 12.1 中文文案（zh.json）

```json
{
  "subscription": {
    "dataSubscription": "数据订阅",
    "subscribe": "订阅",
    "subscribeByFilter": "按此条件订阅",
    "ruleManagement": "订阅规则管理",
    "createRule": "新建规则",
    "editRule": "编辑规则",
    "viewRule": "查看规则",
    "ruleName": "规则名称",
    "organization": "所属组织",
    "targetModel": "目标模型",
    "filterType": "筛选类型",
    "filterTypeCondition": "过滤条件",
    "filterTypeInstances": "实例选择",
    "selectInstances": "选择实例",
    "triggerType": "触发类型",
    "triggerTypeAttributeChange": "属性变化",
    "triggerTypeRelationChange": "关联变化",
    "triggerTypeExpiration": "临近到期",
    "attributeChangeDesc": "监听指定字段的值变化",
    "relationChangeDesc": "监听关联实例的新增或删除",
    "expirationDesc": "监听时间字段临近到期",
    "watchFields": "监听字段",
    "relatedModel": "关联模型",
    "relatedFields": "关联字段",
    "timeField": "时间字段",
    "daysBefore": "提前天数",
    "naturalDays": "自然日",
    "recipients": "接收对象",
    "selectUsers": "选择用户",
    "selectGroups": "选择用户组",
    "notificationChannel": "通知渠道",
    "status": "状态",
    "enabled": "启用",
    "disabled": "停用",
    "lastTriggeredAt": "最近触发时间",
    "saveAndEnable": "保存并启用",
    "saveOnly": "仅保存",
    "cancel": "取消",
    "maxConditions": "最多 8 个条件",
    "andLogic": "且（AND）",
    "onlyOwnerCanManage": "仅限所属组织管理",
    "atLeastOneRecipient": "至少选择一个接收对象",
    "atLeastOneTriggerType": "至少选择一种触发类型",
    "deleteConfirm": "确定要删除该订阅规则吗？",
    "toggleEnableConfirm": "确定要启用该订阅规则吗？",
    "toggleDisableConfirm": "确定要停用该订阅规则吗？"
  }
}
```

### 12.2 英文文案（en.json）

```json
{
  "subscription": {
    "dataSubscription": "Data Subscription",
    "subscribe": "Subscribe",
    "subscribeByFilter": "Subscribe by Filter",
    "ruleManagement": "Subscription Rule Management",
    "createRule": "Create Rule",
    "editRule": "Edit Rule",
    "viewRule": "View Rule",
    "ruleName": "Rule Name",
    "organization": "Organization",
    "targetModel": "Target Model",
    "filterType": "Filter Type",
    "filterTypeCondition": "Filter Condition",
    "filterTypeInstances": "Instance Selection",
    "selectInstances": "Select Instances",
    "triggerType": "Trigger Type",
    "triggerTypeAttributeChange": "Attribute Change",
    "triggerTypeRelationChange": "Relation Change",
    "triggerTypeExpiration": "Near Expiration",
    "attributeChangeDesc": "Monitor value changes of specified fields",
    "relationChangeDesc": "Monitor addition or removal of related instances",
    "expirationDesc": "Monitor time fields approaching expiration",
    "watchFields": "Watch Fields",
    "relatedModel": "Related Model",
    "relatedFields": "Related Fields",
    "timeField": "Time Field",
    "daysBefore": "Days Before",
    "naturalDays": "natural days",
    "recipients": "Recipients",
    "selectUsers": "Select Users",
    "selectGroups": "Select Groups",
    "notificationChannel": "Notification Channel",
    "status": "Status",
    "enabled": "Enabled",
    "disabled": "Disabled",
    "lastTriggeredAt": "Last Triggered At",
    "saveAndEnable": "Save & Enable",
    "saveOnly": "Save Only",
    "cancel": "Cancel",
    "maxConditions": "Max 8 conditions",
    "andLogic": "AND",
    "onlyOwnerCanManage": "Only owner organization can manage",
    "atLeastOneRecipient": "At least one recipient is required",
    "atLeastOneTriggerType": "At least one trigger type is required",
    "deleteConfirm": "Are you sure you want to delete this subscription rule?",
    "toggleEnableConfirm": "Are you sure you want to enable this subscription rule?",
    "toggleDisableConfirm": "Are you sure you want to disable this subscription rule?"
  }
}
```
