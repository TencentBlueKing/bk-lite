import { render } from '@testing-library/react';

import { AtomIcon } from '../components/atom-icon';
import type { WorkflowTriggerType } from '../lib/types';

function iconHref(container: HTMLElement) {
  const use = container.querySelector('use');
  return use?.getAttribute('href') || use?.getAttribute('xlink:href');
}

describe('触发器图标', () => {
  it.each<[WorkflowTriggerType, string]>([
    ['FORM', '#icon-biaodan'],
    ['SCHEDULE', '#icon-a-icon-dingshichufa1x'],
    ['WEBHOOK', '#icon-RESTfulAPI'],
    ['NATS', '#icon-WebSphereMQ'],
  ])('%s 使用独立图标 %s', (triggerType, href) => {
    const { container } = render(<AtomIcon nodeType="TRIGGER" triggerType={triggerType} />);
    expect(iconHref(container)).toBe(href);
    expect(container.querySelector('[data-testid="atom-icon-trigger"]')).toBeNull();
  });

  it('未标明入口类型时仍用闪电', () => {
    const { getByTestId } = render(<AtomIcon nodeType="TRIGGER" />);
    expect(getByTestId('atom-icon-trigger').querySelector('.anticon-thunderbolt')).not.toBeNull();
  });
});

describe('与 OpsPilot 工作台对齐的节点图标', () => {
  it.each<[string, string]>([
    ['bklite_agent', '#icon-zhinengti'],
    ['bklite_intent_classification', '#icon-question-circle-fill'],
    ['bklite_memory_read', '#icon-zhishiku2'],
    ['bklite_memory_write', '#icon-zhishiku'],
    ['bklite_notification', '#icon-alarm'],
    ['bklite_http_request', '#icon-HTTP'],
  ])('%s 使用 %s', (atomKey, href) => {
    const { container } = render(<AtomIcon nodeType="ACTION" atomKey={atomKey} />);
    expect(iconHref(container)).toBe(href);
  });

  it('条件分支使用工作台的分支图标，作业和报告保持原图标', () => {
    const condition = render(<AtomIcon nodeType="CONTROL" controlKind="condition" />);
    expect(iconHref(condition.container)).toBe('#icon-tiaojianfenzhi');
    condition.unmount();

    const job = render(<AtomIcon nodeType="ACTION" category="作业平台" atomKey="bklite_job_execute" />);
    expect(iconHref(job.container)).toBe('#icon-job');
    job.unmount();

    const report = render(<AtomIcon nodeType="ACTION" category="报告" atomKey="bklite_document_render" />);
    expect(iconHref(report.container)).toBe('#icon-Word');
    report.unmount();

    const transform = render(<AtomIcon nodeType="ACTION" category="报告" atomKey="bklite_data_transform" />);
    expect(iconHref(transform.container)).toBe('#icon-shujucaiji');
    transform.unmount();

    const approval = render(<AtomIcon nodeType="CONTROL" controlKind="approval" />);
    expect(iconHref(approval.container)).toBe('#icon-rengongganyu');
  });
});
