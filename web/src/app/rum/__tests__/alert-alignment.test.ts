import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOT = join(process.cwd(), 'src/app/rum');

describe('rum alert alignment page skeleton', () => {
  const alerts = readFileSync(join(ROOT, 'alert-events/page.tsx'), 'utf8');
  const policies = readFileSync(join(ROOT, 'monitors/page.tsx'), 'utf8');
  const form = readFileSync(join(ROOT, 'monitors/ui/monitor-form-drawer.tsx'), 'utf8');
  const channels = readFileSync(join(ROOT, 'monitors/ui/notification-target-fields.tsx'), 'utf8');
  const actions = readFileSync(join(ROOT, 'alert-events/alert-handler-actions.tsx'), 'utf8');

  it('locks alert tabs, filters, columns, empty headers, and the event query', () => {
    expect(alerts).toContain("t('rum.alertEvents.tabActive', '活跃告警')");
    expect(alerts).toContain("t('rum.alertEvents.tabHistory', '历史告警')");
    expect(alerts).toContain("t('rum.alertEvents.searchPlaceholder', '搜索告警…')");
    expect(alerts).toContain("t('rum.filter.allApps', '全部应用')");
    expect(alerts).toContain("t('rum.alertEvents.name', '名称')");
    expect(alerts).toContain("t('rum.alertEvents.severity', '级别')");
    expect(alerts).toContain("t('rum.alertEvents.status', '状态')");
    expect(alerts).toContain("t('rum.alertEvents.metricValue', '指标 / 值')");
    expect(alerts).toContain("t('rum.applications.application', '应用')");
    expect(alerts).toContain("t('rum.alertEvents.firedAt', '触发时间')");
    expect(alerts).toContain('emptyText');
    expect(alerts).toContain("<CustomTable");
    expect(alerts).toContain("searchParams.get('event')");
    expect(alerts).toContain('href="/alarm/alarms"');
    expect(alerts).toContain("t('rum.alertEvents.handlers', '处理人')");
    expect(alerts).toContain("t('rum.alertEvents.notification', '通知')");
    expect(alerts).toContain("t('rum.alertEvents.myAlert', '我的告警')");
    expect(alerts).toContain('AlertHandlerActions');
    expect(actions).toContain('canClaimOrAssign');
    expect(actions).toContain('canReassign');
    expect(actions).toContain('canClose');
    expect(actions).toContain("usePermissions('/rum/alert-events')");
    expect(actions).not.toContain('zIndex={99999}');
    expect(actions).toContain("alert.status === 'active'");
    expect(alerts).toContain("t('rum.alertEvents.retry', '重投')");
    expect(alerts).toContain('ev.handlersDisplay || ev.handlers');
    expect(alerts).toContain('alert.handlersDisplay || alert.handlers');
    expect(alerts).not.toContain('Segmented');
  });

  it('locks policy columns and the channel selector fields', () => {
    expect(policies).toContain("t('rum.monitors.handlers', '处理人')");
    expect(policies).toContain("t('rum.monitors.organizations', '组织')");
    expect(form).toContain("t('rum.monitors.handlers', '处理人')");
    expect(policies).toContain("t('rum.monitors.lastEvaluation', '最近判定')");
    expect(policies).toContain('m.handlersDisplay || m.handlers');
    expect(policies).toContain("if (metric === 'session_count') return String(Math.round(value));");
    expect(policies).toContain('m.forDurationSec > 0 ?');
    expect(policies).toContain('emptyText');
    expect(form).toContain('GroupTreeSelect');
    expect(form).toContain('evaluationWindowMinutes');
    expect(form).toContain('forDurationSec');
    expect(form).toContain('noDataAfter');
    expect(form).toContain('NotificationTargetFields');
    expect(form).not.toContain('notifyChannels');
    expect(channels).toContain("t('rum.monitors.alertCopy', '告警中心副本')");
    expect(channels).toContain("t('rum.monitors.plainNotice', '普通通知')");
    expect(channels).toContain('recipientMode');
  });
});
