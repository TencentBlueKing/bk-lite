import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import CloudEventGuide, { isCloudEventGuideSource } from '../cloudEventGuide';
import type { AlertSourceIntegrationGuide } from '../../types/integration';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/useCopy', () => ({ useCopy: () => ({ copy: vi.fn() }) }));

afterEach(cleanup);
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
  });
});

const aliyunGuide: AlertSourceIntegrationGuide = {
  source_type: 'aliyun_eventbridge',
  source_id: 'aliyun_eventbridge',
  webhook_url: 'https://alerts.example.com/api/v1/alerts/api/source/aliyun_eventbridge/webhook/',
  description: '原始 JSON',
  sections: [{ title: '阿里云控制台怎么填', paragraphs: ['不要订 ActionTrail 和 Config。'] }],
  field_mapping_note: '下表是平台写入事件的取值。',
  field_mapping: [
    { field: 'title', from: '目录中文名 + resource_id', detail: '不读报文里的标题' },
    { field: 'external_id', from: 'aliyunaccountid + data.eventId', detail: '产生和恢复必须相同' },
    { field: 'resource_id', from: '实例用 data.instanceId；磁盘用 data.diskId', detail: '磁盘 ID 不拿去对 CMDB' },
  ],
  example_items: [
    {
      title: '发生：系统错误导致实例重启',
      explain: '阶段 Executing。',
      lands: ['title = 因系统错误实例重启 i-bp1', 'action = created'],
      curl: "SECRET: {{TEAM_SECRET}}\necs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]",
    },
  ],
  examples: { Python: "headers = {'SECRET': '{{TEAM_SECRET}}'}" },
  report_fields: [
    { event: 'SystemFailure.Reboot', title: '因系统错误实例重启', level: '0', resource: 'instance', stateless: false },
  ],
  catalog_text: 'Executing 发生',
};

it('uses the cloud guide only for the two builtin sources', () => {
  expect(isCloudEventGuideSource('aliyun_eventbridge')).toBe(true);
  expect(isCloudEventGuideSource('tencent_eventbus')).toBe(true);
  expect(isCloudEventGuideSource('restful')).toBe(false);
});

it('shows the field mapping, the stored result, and the vendor payload', () => {
  render(<CloudEventGuide guide={aliyunGuide} selectedTeamSecret="org-secret-value" />);

  expect(screen.getByText('integration.baseInfo')).toBeTruthy();
  expect(screen.getByText('integration.eventFieldsMapping')).toBeTruthy();
  expect(screen.getByText('integration.eventFieldsDescription')).toBeTruthy();
  expect(screen.getByText('不读报文里的标题')).toBeTruthy();
  expect(screen.getAllByText('external_id').length).toBeGreaterThan(0);
  expect(screen.getByText(/data.eventId/)).toBeTruthy();
  expect(screen.getByText(/data.diskId/)).toBeTruthy();
  expect(screen.getByText(/title = 因系统错误实例重启/)).toBeTruthy();
  expect(screen.getByText(/SystemFailure.Reboot:Executing/)).toBeTruthy();
  expect(screen.getByText(/SECRET: org-secret-value/)).toBeTruthy();
  expect(screen.queryByText(/\{\{TEAM_SECRET\}\}/)).toBeNull();
  expect(screen.queryByText(/Jenkins/)).toBeNull();
  expect(screen.queryByText(/receiver_data/)).toBeNull();
  expect(screen.getByText('SystemFailure.Reboot')).toBeTruthy();
});

it('does not show a loopback callback address', () => {
  render(
    <CloudEventGuide
      guide={{
        ...aliyunGuide,
        webhook_url: 'http://127.0.0.1:8000/api/v1/alerts/api/source/aliyun_eventbridge/webhook/',
      }}
    />,
  );
  expect(screen.queryByText(/127\.0\.0\.1/)).toBeNull();
  expect(screen.getAllByText(/\{url\}\/api\/v1\/alerts\/api\/source\/aliyun_eventbridge\/webhook\//).length).toBeGreaterThan(0);
});

it('keeps the secret placeholder until an organization is selected', () => {
  render(<CloudEventGuide guide={aliyunGuide} />);
  expect(screen.getAllByText(/\{\{TEAM_SECRET\}\}/).length).toBeGreaterThan(0);
});

it('shows the tencent query secret url', () => {
  const guide: AlertSourceIntegrationGuide = {
    ...aliyunGuide,
    source_id: 'tencent_eventbus',
    webhook_url_with_secret: 'https://alerts.example.com/api/v1/alerts/api/source/tencent_eventbus/webhook/?secret={{TEAM_SECRET}}',
    example_items: [{
      title: '发生：监控告警模板',
      explain: '',
      lands: ['resource_id = ins-test-1'],
      curl: '"unInstanceId": "ins-test-1"\nSECRET: {{TEAM_SECRET}}',
    }],
  };
  render(<CloudEventGuide guide={guide} selectedTeamSecret="org-secret-value" />);
  expect(screen.getByText(/unInstanceId/)).toBeTruthy();
  expect(screen.getByText(/secret=org-secret-value/)).toBeTruthy();
});
