import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ApmPolicyEditor from '../policy-editor';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { HandledRequestError } from '@/utils/request';

const { chartRender } = vi.hoisted(() => ({ chartRender: vi.fn() }));

const input = {
  name: '错误率策略',
  service_id: 'svc-1',
  organizations: [10],
  environment: 'production',
  alert_name: '${service}',
  endpoints: ['POST /checkout'],
  version_mode: 'all' as const,
  versions: [],
  metric_type: 'error_rate' as const,
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'avg' as const,
  thresholds: [{ severity: 'warning' as const, comparator: 'gt' as const, value: '0.05' }],
  trigger_after: 3,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '' as const,
  no_data_alert_name: '',
  notification_targets: [],
};
const policy = {
  ...input,
  id: 'p1',
  is_enabled: true,
  service_namespace: 'shop',
  service_name: 'checkout',
  state: null,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
};
const api = {
  createPolicy: vi.fn(),
  deletePolicy: vi.fn(),
  getInstances: vi.fn(),
  getNotificationChannels: vi.fn(),
  getNotificationRecipients: vi.fn(),
  getPolicy: vi.fn(),
  getServiceRed: vi.fn(),
  getServices: vi.fn(),
  isLoading: false,
  previewPolicy: vi.fn(),
  dryRunPolicy: vi.fn(),
  updatePolicy: vi.fn(),
};
vi.mock('next/link', () => ({ default: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/group-tree-select', () => ({
  default: ({
    value = [],
    onChange,
    placeholder,
  }: {
    value?: number[];
    onChange?: (next: number[]) => void;
    placeholder?: string;
  }) => (
    <button type="button" aria-label={placeholder || '选择组织'} onClick={() => onChange?.([10])}>
      {(value || []).join(',') || placeholder}
    </button>
  ),
}));
vi.mock('@/components/time-series-composed-chart', () => ({
  default: (props: { series: Array<Record<string, unknown>> }) => {
    chartRender(props);
    return <div>真实趋势图</div>;
  },
}));

beforeEach(() => {
  window.matchMedia = vi
    .fn()
    .mockReturnValue({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
  api.getServices.mockResolvedValue([{
    id: 'svc-1',
    namespace: 'shop',
    name: 'checkout',
    archived_at: null,
    organization_ids: [10],
    environment_views: [{ environment: 'production' }],
  }]);
  api.getNotificationChannels.mockResolvedValue([]);
  api.getNotificationRecipients.mockResolvedValue([
    { id: 7, username: 'bob', display_name: 'Bob' },
  ]);
  api.getPolicy.mockResolvedValue(policy);
  api.getServiceRed.mockResolvedValue({ top_endpoints: [{ endpoint: 'POST /checkout' }], timeseries: [] });
  api.getInstances.mockResolvedValue([]);
  api.previewPolicy.mockResolvedValue({
    value: '0.2',
    breached: true,
    evaluated_at: '2026-08-14T02:00:00Z',
    data_state: 'available',
    threshold: input.thresholds[0],
    series: [{ timestamp: '2026-08-14T02:00:00Z', request_rate: 10, error_rate: 0.2, p95_ms: 100, p99_ms: 150 }],
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 四步策略编辑器', { timeout: 15000 }, () => {
  it('展示约定的四步字段和真实变量来源，且不暴露 Monitor/Log 表达式', async () => {
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    expect(await screen.findByText('基本信息')).not.toBeNull();
    expect(screen.getByText('指标定义')).not.toBeNull();
    expect(screen.getByText('告警条件')).not.toBeNull();
    expect(screen.getByText('通知配置')).not.toBeNull();
    expect(screen.getByText('告警阈值')).not.toBeNull();
    expect(screen.getAllByText('当结果是')).toHaveLength(3);
    expect(screen.getByLabelText('严重阈值')).not.toBeNull();
    expect(screen.getByLabelText('错误阈值')).not.toBeNull();
    expect(screen.getByLabelText('警告阈值')).not.toBeNull();
    expect(screen.getByText('${endpoint}')).not.toBeNull();
    expect(screen.queryByLabelText('环境（必选）')).toBeNull();
    expect(screen.getByLabelText('端点')).not.toBeNull();
    expect(screen.queryByLabelText('版本维度')).toBeNull();
    expect(screen.getAllByLabelText('告警名称')).toHaveLength(1);
    expect(screen.queryByText(/LogSQL|MonitorObject|采集插件/)).toBeNull();
    expect(screen.getByRole('switch', { name: '启用通知' })).not.toBeNull();
    const organizationLabel = screen.getByText('所属组织');
    const handlerLabel = screen.getByText('处理人');
    expect(organizationLabel).not.toBeNull();
    expect(handlerLabel).not.toBeNull();
    expect(
      organizationLabel.compareDocumentPosition(handlerLabel)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('启用无数据告警后展示无数据告警名称', async () => {
    api.getPolicy.mockResolvedValue({
      ...policy,
      no_data_after: 5,
      no_data_severity: 'warning',
      no_data_alert_name: '${service} 无数据告警',
    });
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findAllByLabelText('告警名称')).toHaveLength(2);
  });

  it('新策略按渠道能力逐个添加通知目标，并能远程搜索首批目录之外的系统用户', async () => {
    const user = userEvent.setup();
    api.getNotificationChannels.mockResolvedValue([
      {
        id: 21,
        name: '邮件',
        channel_type: 'email',
        description: '邮件通知',
        delivery_mode: 'message',
        recipient_mode: 'system_user',
        availability: 'available',
      },
      {
        id: 22,
        name: 'Webhook',
        channel_type: 'custom_webhook',
        description: '外部值班通知',
        delivery_mode: 'message',
        recipient_mode: 'free_text',
        availability: 'available',
      },
      {
        id: 23,
        name: '告警中心',
        channel_type: 'nats',
        description: '事件副本',
        delivery_mode: 'alert_event_copy',
        recipient_mode: 'none',
        availability: 'available',
      },
    ]);
    api.getNotificationRecipients.mockImplementation(({ search }: { search?: string } = {}) =>
      Promise.resolve(search === 'late'
        ? [{ id: 142, username: 'late-user', display_name: 'Late User' }]
        : []));
    renderWithApmIntl(<ApmPolicyEditor />);

    await user.click(await screen.findByRole('switch', { name: '启用通知' }));
    await user.click(screen.getByRole('button', { name: /邮件.*普通通知/ }));
    const recipientSearch = await screen.findByLabelText('系统用户 ID');
    await user.click(recipientSearch);
    await user.type(recipientSearch, 'late');
    await waitFor(() => expect(api.getNotificationRecipients).toHaveBeenLastCalledWith({ search: 'late', limit: 100 }));
    expect(api.getNotificationRecipients.mock.calls.filter(([params]) => params?.search)).toEqual([
      [{ search: 'late', limit: 100 }],
    ]);
    await user.click(await screen.findByText('Late User (late-user)'));

    await user.click(screen.getByRole('button', { name: /Webhook.*普通通知/ }));
    expect(screen.getByLabelText('通知对象')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: /告警中心.*告警中心副本/ }));
    expect(screen.getByText('该渠道接收告警事件副本，无需配置接收人。')).not.toBeNull();
  });

  it('编辑时按 system_user、free_text、none 分别回显并提交原始接收人', async () => {
    const user = userEvent.setup();
    api.getNotificationChannels.mockResolvedValue([
      { id: 21, name: '邮件', channel_type: 'email', description: '', delivery_mode: 'message', recipient_mode: 'system_user', availability: 'available' },
      { id: 22, name: 'Webhook', channel_type: 'custom_webhook', description: '', delivery_mode: 'message', recipient_mode: 'free_text', availability: 'available' },
      { id: 23, name: '告警中心', channel_type: 'nats', description: '', delivery_mode: 'alert_event_copy', recipient_mode: 'none', availability: 'available' },
    ]);
    api.getNotificationRecipients.mockResolvedValue([{ id: 42, username: 'alice', display_name: 'Alice' }]);
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        { channel_id: 21, channel_name: '邮件', channel_type: 'email', delivery_mode: 'message', recipient_mode: 'system_user', recipients: ['42'] },
        { channel_id: 22, channel_name: 'Webhook', channel_type: 'custom_webhook', delivery_mode: 'message', recipient_mode: 'free_text', recipients: ['on-call@example.com'] },
        { channel_id: 23, channel_name: '告警中心', channel_type: 'nats', delivery_mode: 'alert_event_copy', recipient_mode: 'none', recipients: [] },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findByText('Alice (alice)')).not.toBeNull();
    expect(screen.getByText('on-call@example.com')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        notification_targets: [
          { channel_id: 21, recipients: ['42'] },
          { channel_id: 22, recipients: ['on-call@example.com'] },
          { channel_id: 23, recipients: [] },
        ],
      }),
    ));
  });

  it('none 渠道会清理历史遗留接收人', async () => {
    const user = userEvent.setup();
    api.getNotificationChannels.mockResolvedValue([
      { id: 23, name: '告警中心', channel_type: 'nats', description: '', delivery_mode: 'alert_event_copy', recipient_mode: 'none', availability: 'available' },
    ]);
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        { channel_id: 23, channel_name: '告警中心', channel_type: 'nats', delivery_mode: 'alert_event_copy', recipient_mode: 'none', recipients: ['stale'] },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ notification_targets: [{ channel_id: 23, recipients: [] }] }),
    ));
  });

  it('接收人目录故障时仍回显已有稳定 ID，但禁止新增', async () => {
    api.getNotificationChannels.mockResolvedValue([
      { id: 21, name: '邮件', channel_type: 'email', description: '', delivery_mode: 'message', recipient_mode: 'system_user', availability: 'available' },
    ]);
    api.getNotificationRecipients.mockRejectedValue(new HandledRequestError('unavailable', { status: 503 }));
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        { channel_id: 21, channel_name: '邮件', channel_type: 'email', delivery_mode: 'message', recipient_mode: 'system_user', recipients: ['42'] },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findByText('用户 42（当前不可用）')).not.toBeNull();
    expect(screen.getByLabelText('系统用户 ID').closest('.ant-select')?.className).toContain('ant-select-disabled');
  });

  it('渠道目录故障不会把历史渠道误判为失效', async () => {
    const user = userEvent.setup();
    api.getNotificationChannels.mockRejectedValue(new HandledRequestError('unavailable', { status: 503 }));
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        { channel_id: 23, channel_name: '告警中心', channel_type: 'nats', delivery_mode: 'alert_event_copy', recipient_mode: 'none', recipients: [] },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    expect(await screen.findByText('暂时无法读取系统通知渠道')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled());
    expect(screen.queryByText('已失效，保存前请移除')).toBeNull();
  });

  it('页面加载后自动把当前指标配置提交给真实预览接口', async () => {
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await waitFor(() =>
      expect(api.previewPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          service_id: 'svc-1',
          environment: 'production',
          endpoints: ['POST /checkout'],
          version_mode: 'all',
          metric_type: 'error_rate',
          thresholds: [expect.objectContaining({ severity: 'warning', value: 0.05 })],
        }),
        true,
      ),
    { timeout: 3000 },
    );
    expect(await screen.findByText('真实趋势图')).not.toBeNull();
    const previewSeries = chartRender.mock.calls.at(-1)?.[0].series;
    expect(previewSeries).toEqual([
      expect.objectContaining({
        color: '#5B8FF9',
        smooth: false,
        lineWidth: 1,
        areaOpacity: 0.36,
      }),
      expect.objectContaining({ color: '#FFAD42', lineWidth: 1 }),
    ]);
  });

  it('阈值变化后防抖自动更新指标预览', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await waitFor(() => expect(api.previewPolicy).toHaveBeenCalled(), { timeout: 3000 });
    api.previewPolicy.mockClear();

    const warningThreshold = screen.getByLabelText('警告阈值');
    await user.clear(warningThreshold);
    await user.type(warningThreshold, '8');

    await waitFor(() =>
      expect(api.previewPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          thresholds: [expect.objectContaining({ severity: 'warning', value: 0.08 })],
        }),
        true,
      ),
    );
  });

  it('新策略可选择端点，并自动使用全部版本', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor />);

    await user.type(await screen.findByLabelText('策略名称'), '新策略');
    await user.click(screen.getByLabelText('服务'));
    await user.click(await screen.findByText('shop / checkout'));
    await user.click(screen.getByLabelText('端点'));
    const endpointOptions = await screen.findAllByText('POST /checkout');
    await user.click(endpointOptions.at(-1)!);

    await waitFor(() =>
      expect(api.previewPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          service_id: 'svc-1',
          environment: 'production',
          endpoints: ['POST /checkout'],
          version_mode: 'all',
          versions: [],
        }),
        true,
      ),
    );
  });

  it('编辑策略时保留归档服务和不可用渠道的名称', async () => {
    const user = userEvent.setup();
    api.getServices.mockResolvedValue([
      {
        id: 'svc-active',
        namespace: 'shop',
        name: 'catalog',
        archived_at: null,
        organization_ids: [10],
        environment_views: [{ environment: 'production' }],
      },
    ]);
    api.getNotificationChannels.mockResolvedValue([
      {
        id: 23,
        name: '告警中心',
        channel_type: 'nats',
        description: '事件副本',
        delivery_mode: 'alert_event_copy',
        recipient_mode: 'none',
        availability: 'unavailable',
      },
    ]);
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        {
          channel_id: 23,
          channel_name: '告警中心',
          channel_type: 'nats',
          delivery_mode: 'alert_event_copy',
          recipient_mode: 'none',
          recipients: [],
        },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findByText('shop / checkout（已归档）')).not.toBeNull();
    expect(screen.getByText('告警中心')).not.toBeNull();
    expect(screen.getByText('已失效，保存前请移除')).not.toBeNull();
    expect(screen.queryByText('svc-1')).toBeNull();
    expect(screen.queryByText('23')).toBeNull();
    expect(api.getServices).toHaveBeenCalledWith({ include_archived: true });

    await user.click(screen.getByRole('button', { name: '保存策略' }));
    expect(await screen.findByText('已失效，保存前请移除')).not.toBeNull();
    expect(api.updatePolicy).not.toHaveBeenCalled();
  });

  it('选服务且组织为空时带入服务组织，保存时提交所属组织', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor />);

    await user.type(await screen.findByLabelText('策略名称'), '新策略');
    expect(screen.getByLabelText('选择组织').textContent).toBe('选择组织');
    await user.click(screen.getByLabelText('服务'));
    await user.click(await screen.findByText('shop / checkout'));
    expect(screen.getByLabelText('选择组织').textContent).toBe('10');

    await user.click(screen.getByRole('button', { name: '创建策略' }));
    await waitFor(() =>
      expect(api.createPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          organizations: [10],
          service_id: 'svc-1',
          handlers: [],
        }),
      ),
    );
  });

  it('按策略组织拉取处理人候选，添加系统用户渠道时不把处理人写入接收人', async () => {
    const user = userEvent.setup();
    api.getPolicy.mockResolvedValue({
      ...policy,
      handlers: [7],
    });
    api.getNotificationChannels.mockResolvedValue([
      {
        id: 21,
        name: '邮件',
        channel_type: 'email',
        description: '邮件通知',
        delivery_mode: 'message',
        recipient_mode: 'system_user',
        availability: 'available',
      },
    ]);
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findByText('处理人')).not.toBeNull();
    await waitFor(() =>
      expect(api.getNotificationRecipients).toHaveBeenCalledWith(
        expect.objectContaining({ organization_ids: '10', limit: 100 }),
      ),
    );

    await user.click(await screen.findByRole('switch', { name: '启用通知' }));
    await user.click(screen.getByRole('button', { name: /邮件.*普通通知/ }));
    const recipients = await screen.findByLabelText('系统用户 ID');
    expect(recipients.closest('.ant-select')?.textContent).not.toContain('7');
  });

  it('截断候选不删除已选处理人，保存仍提交原 User.id', async () => {
    const user = userEvent.setup();
    api.getPolicy.mockResolvedValue({
      ...policy,
      handlers: [101],
    });
    api.getNotificationRecipients.mockResolvedValue(
      Array.from({ length: 100 }, (_, index) => ({
        id: index + 1,
        username: `user${index + 1}`,
        display_name: `User ${index + 1}`,
      })),
    );

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    await waitFor(() =>
      expect(api.getNotificationRecipients).toHaveBeenCalledWith(
        expect.objectContaining({ organization_ids: '10', limit: 100 }),
      ),
    );

    const handlersSelect = await screen.findByLabelText('处理人');
    await waitFor(() => {
      expect(handlersSelect.closest('.ant-select')?.textContent).toContain('101');
    });

    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          handlers: [101],
        }),
      ),
    );
  });

  it('存量策略按当前值保存，错误率阈值仍除以 100，最低请求数缺省为 null', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          compare_mode: 'absolute',
          compare_value_kind: '',
          min_request_count: null,
          thresholds: [expect.objectContaining({ severity: 'warning', value: 0.05 })],
        }),
      ),
    );
  });

  it('相对上一等长窗切换变化量和变化率，阈值单位跟着变且数字不重算', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    expect((await screen.findAllByText('%')).length).toBeGreaterThan(0);

    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('相对上一等长窗'));
    expect(screen.getByRole('radio', { name: '变化量 Δ' })).not.toBeNull();
    expect(screen.getAllByText('个百分点').length).toBeGreaterThan(0);
    expect((screen.getByLabelText('警告阈值') as HTMLInputElement).value).toBe('5');

    await user.click(screen.getByRole('radio', { name: '变化率 %' }));
    expect(screen.queryByText('个百分点')).toBeNull();
    expect((screen.getByLabelText('警告阈值') as HTMLInputElement).value).toBe('5');

    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          compare_mode: 'previous_window',
          compare_value_kind: 'percent',
          thresholds: [expect.objectContaining({ severity: 'warning', value: 5 })],
        }),
      ),
    );
  });

  it('同窗固定变化率并隐藏单选，无流量不提交比较字段', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByLabelText('比较基准'));
    await user.click(await screen.findByText('同窗'));
    expect(screen.queryByRole('radio', { name: '变化量 Δ' })).toBeNull();
    expect(screen.queryByRole('radio', { name: '变化率 %' })).toBeNull();
    const hours = screen.getByLabelText('小时数') as HTMLInputElement;
    expect(hours.value).toBe('1');
    await user.clear(hours);
    await user.type(hours, '6');
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          compare_mode: 'offset_hours',
          compare_offset_amount: 6,
          compare_value_kind: 'percent',
        }),
      ),
    );

    await user.click(screen.getByLabelText('指标'));
    await user.click(await screen.findByRole('option', { name: '无流量' }));
    expect(screen.queryByLabelText('比较基准')).toBeNull();
    expect(screen.queryByLabelText('最低请求数')).toBeNull();
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled());
    const payload = api.updatePolicy.mock.calls.at(-1)?.[1];
    expect(payload.metric_type).toBe('no_traffic');
    expect(payload).not.toHaveProperty('compare_mode');
    expect(payload).not.toHaveProperty('compare_offset_amount');
    expect(payload).not.toHaveProperty('compare_value_kind');
    expect(payload).not.toHaveProperty('min_request_count');
    expect(payload).not.toHaveProperty('slow_threshold_ms');
    expect(payload).not.toHaveProperty('apdex_threshold_ms');
  });

  it('新建策略默认最低请求数 20，清空后保存为 null', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor />);
    await user.type(await screen.findByLabelText('策略名称'), '新策略');
    await user.click(screen.getByLabelText('服务'));
    await user.click(await screen.findByText('shop / checkout'));
    expect((screen.getByLabelText('最低请求数') as HTMLInputElement).value).toBe('20');
    await user.clear(screen.getByLabelText('最低请求数'));
    await user.click(screen.getByRole('button', { name: '创建策略' }));
    await waitFor(() =>
      expect(api.createPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          compare_mode: 'absolute',
          compare_value_kind: '',
          min_request_count: null,
          metric_type: 'error_rate',
        }),
      ),
    );
  });

  it('未填策略名时试算使用预览名称，不要求先保存', async () => {
    const user = userEvent.setup();
    api.dryRunPolicy.mockResolvedValue({
      evaluated_at: '2026-08-14T02:00:00Z',
      compare_mode: 'absolute',
      compare_value_kind: '',
      result_unit: 'ratio',
      total_targets: 1,
      truncated: false,
      items: [],
    });
    renderWithApmIntl(<ApmPolicyEditor />);
    await user.click(await screen.findByLabelText('服务'));
    await user.click(await screen.findByText('shop / checkout'));
    await user.click(screen.getByRole('button', { name: '试算' }));
    await waitFor(() =>
      expect(api.dryRunPolicy).toHaveBeenCalledWith(
        expect.objectContaining({ name: '指标预览', service_id: 'svc-1' }),
      ),
    );
    expect(api.createPolicy).not.toHaveBeenCalled();
  });

  it('试算表展示结论、截断提示和连续命中文案', async () => {
    const user = userEvent.setup();
    api.dryRunPolicy.mockResolvedValue({
      evaluated_at: '2026-08-14T02:00:00Z',
      compare_mode: 'previous_window',
      compare_value_kind: 'percent',
      result_unit: 'percent',
      total_targets: 21,
      truncated: true,
      items: [
        {
          endpoint: 'POST /checkout',
          version: 'v2',
          verdict: 'would_trigger',
          current_value: '0.06',
          baseline_value: '0.04',
          compared_value: '50',
          request_count: 12,
          matched_threshold: { severity: 'error', comparator: 'gt', value: '40' },
          reason: '本轮命中 1/3，现网不会建告警',
        },
        {
          endpoint: 'GET /cart',
          version: '',
          verdict: 'insufficient_samples',
          current_value: '0.5',
          baseline_value: null,
          compared_value: null,
          request_count: 8,
          matched_threshold: null,
          reason: '样本不足',
        },
      ],
    });
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByRole('button', { name: '试算' }));
    expect(await screen.findByText('共 21 个目标，只试算前 20 个，请在端点里缩小范围')).not.toBeNull();
    expect(screen.getByText('将触发')).not.toBeNull();
    expect(screen.getAllByText('样本不足').length).toBeGreaterThan(0);
    expect(screen.getByText('本轮命中 1/3，现网不会建告警')).not.toBeNull();
    expect(screen.getByText('POST /checkout v2')).not.toBeNull();
    expect(api.dryRunPolicy).toHaveBeenCalledWith(expect.objectContaining({ policy_id: 'p1' }));
  });

  it('分组指标下拉出现慢阈值和 Apdex T，计数类隐藏汇聚方法', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByLabelText('指标'));
    expect(await screen.findByText('时延')).not.toBeNull();
    expect(screen.getByRole('option', { name: 'P95' })).not.toBeNull();
    expect(screen.queryByRole('option', { name: 'P95 延迟' })).toBeNull();
    await user.click(await screen.findByRole('option', { name: '慢请求数' }));
    expect(screen.queryByLabelText('汇聚方法')).toBeNull();
    const slow = screen.getByLabelText('慢阈值 (ms)') as HTMLInputElement;
    await user.clear(slow);
    await user.type(slow, '1000');
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          metric_type: 'slow_request_count',
          slow_threshold_ms: 1000,
          aggregation: 'avg',
        }),
      ),
    );
    const slowPayload = api.updatePolicy.mock.calls.at(-1)?.[1];
    expect(slowPayload.apdex_threshold_ms).toBeNull();
    expect(slowPayload.min_request_count).toBeNull();

    await user.click(screen.getByLabelText('指标'));
    await user.click(await screen.findByRole('option', { name: 'Apdex' }));
    expect((screen.getByLabelText('T (ms)') as HTMLInputElement).value).toBe('500');
    await user.click(screen.getByLabelText('指标'));
    await user.click(await screen.findByRole('option', { name: '错误数' }));
    expect(screen.queryByLabelText('汇聚方法')).toBeNull();
    expect(screen.queryByLabelText('慢阈值 (ms)')).toBeNull();
  });

  it('触发方式提交周期窗口，恢复阈值单位跟着比较基准且数字不重算', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await screen.findByRole('combobox', { name: '触发方式' });
    expect(screen.queryByText('前置条件')).toBeNull();

    await user.click(screen.getByRole('combobox', { name: '触发方式' }));
    await user.click(await screen.findByText('在最近 N 个周期内'));
    expect((screen.getByRole('spinbutton', { name: '周期数' }) as HTMLInputElement).value).toBe('3');

    const recovery = screen.getByRole('spinbutton', { name: '恢复阈值' }) as HTMLInputElement;
    await user.clear(recovery);
    await user.type(recovery, '40');
    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('相对上一等长窗'));
    await user.click(screen.getByRole('radio', { name: '变化率 %' }));
    expect((screen.getByRole('spinbutton', { name: '恢复阈值' }) as HTMLInputElement).value).toBe('40');

    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled());
    const payload = api.updatePolicy.mock.calls.at(-1)?.[1];
    expect(payload).not.toHaveProperty('guard_conditions');
    expect(payload.trigger_window).toBe(3);
    expect(payload.recovery_threshold).toEqual({ comparator: 'lt', value: 40 });
  });

  it('近 N 天同窗均值提交 2 到 7 天，并允许变化量', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByLabelText('比较基准'));
    await user.click(await screen.findByText('近 N 天同窗均值'));
    const days = screen.getByLabelText('天数') as HTMLInputElement;
    expect(days.value).toBe('7');
    expect((screen.getByRole('radio', { name: '变化率 %' }) as HTMLInputElement).checked).toBe(true);
    await user.clear(days);
    await user.type(days, '3');
    await user.click(screen.getByRole('radio', { name: '变化量 Δ' }));
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() =>
      expect(api.updatePolicy).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({
          compare_mode: 'baseline_days',
          compare_offset_amount: 3,
          compare_value_kind: 'delta',
        }),
      ),
    );
  });

  it('同窗和近 N 天切换不沿用对方的数字，Apdex 把恢复比较符翻到对侧', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByLabelText('比较基准'));
    await user.click(await screen.findByText('近 N 天同窗均值'));
    expect((screen.getByLabelText('天数') as HTMLInputElement).value).toBe('7');

    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('同窗'));
    const hours = screen.getByLabelText('小时数') as HTMLInputElement;
    expect(hours.value).toBe('1');
    await user.clear(hours);
    await user.type(hours, '6');
    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('近 N 天同窗均值'));
    expect((screen.getByLabelText('天数') as HTMLInputElement).value).toBe('7');

    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('同窗'));
    await user.click(screen.getByRole('combobox', { name: '对照方式' }));
    await user.click(await screen.findByText('N 天前'));
    const offsetDays = screen.getByLabelText('天数') as HTMLInputElement;
    await user.clear(offsetDays);
    await user.type(offsetDays, '3');
    await user.click(screen.getByLabelText('比较基准'));
    await user.click(await screen.findByText('近 N 天同窗均值'));
    expect((screen.getByLabelText('天数') as HTMLInputElement).value).toBe('3');

    await user.click(screen.getByLabelText('指标'));
    await user.click(await screen.findByRole('option', { name: 'Apdex' }));
    await user.type(screen.getByRole('spinbutton', { name: '恢复阈值' }), '40');
    await user.click(screen.getByRole('button', { name: '保存策略' }));
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled());
    const payload = api.updatePolicy.mock.calls.at(-1)?.[1];
    expect(payload.metric_type).toBe('apdex');
    expect(payload.compare_mode).toBe('baseline_days');
    expect(payload.compare_offset_amount).toBe(3);
    expect(payload.recovery_threshold).toEqual({ comparator: 'gt', value: 40 });
    expect(payload.thresholds).toEqual([expect.objectContaining({ comparator: 'lt', value: 5 })]);
  });
});
