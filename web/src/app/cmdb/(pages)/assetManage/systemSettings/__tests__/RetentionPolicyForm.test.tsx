import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RetentionPolicyForm from '../RetentionPolicyForm';

declare module '@vitest/expect' {
  interface Assertion<T = unknown> {
    toBeDisabled: () => T;
    toBeInTheDocument: () => T;
  }
}

expect.extend({
  toBeDisabled(received: Element) {
    const pass = received instanceof HTMLButtonElement && received.disabled;
    return {
      pass,
      message: () => `expected button ${pass ? 'not ' : ''}to be disabled`,
    };
  },
  toBeInTheDocument(received: Element | null) {
    const pass = received != null && received.ownerDocument.contains(received);
    return {
      pass,
      message: () => `expected element ${pass ? 'not ' : ''}to be in the document`,
    };
  },
});

const tMap: Record<string, string> = {
  'SystemSettings.retentionTitle': '操作日志保留策略',
  'SystemSettings.modeOff': '不清理',
  'SystemSettings.modeDays': '按时长',
  'SystemSettings.modeCount': '按条数',
  'SystemSettings.days': '保留天数',
  'SystemSettings.count': '保留条数',
  'SystemSettings.save': '保存',
  'SystemSettings.running': '正在清理',
  'SystemSettings.lastRun': '上次清理',
  'SystemSettings.deletedCount': '删除条数',
  'SystemSettings.confirmTitle': '确认清理',
  'SystemSettings.confirmContent': '将按策略删除超出范围的操作日志，不可恢复',
};

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => tMap[key] || key }),
}));

const confirm = vi.hoisted(() => vi.fn((opts: { onOk?: () => void }) => opts.onOk?.()));
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, Modal: { ...actual.Modal, confirm } };
});

afterEach(() => {
  cleanup();
  confirm.mockClear();
});

const idleJob = {
  status: 'idle' as const,
  started_at: null,
  finished_at: null,
  deleted_count: 0,
  error: '',
  trigger: '',
};

describe('RetentionPolicyForm', () => {
  it('saves off without confirm', () => {
    const onSave = vi.fn();
    render(
      <RetentionPolicyForm
        policy={{ mode: 'off', days: null, count: null }}
        job={idleJob}
        saving={false}
        onSave={onSave}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(confirm).not.toHaveBeenCalled();
    expect(onSave).toHaveBeenCalledWith({ mode: 'off', days: null, count: null });
  });

  it('confirms before saving by_days', () => {
    const onSave = vi.fn();
    render(
      <RetentionPolicyForm
        policy={{ mode: 'off', days: null, count: null }}
        job={idleJob}
        saving={false}
        onSave={onSave}
      />
    );
    fireEvent.click(screen.getByLabelText('按时长'));
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(confirm).toHaveBeenCalled();
    expect(onSave).toHaveBeenCalledWith({ mode: 'by_days', days: 180, count: null });
  });

  it('disables save while running', () => {
    render(
      <RetentionPolicyForm
        policy={{ mode: 'off', days: null, count: null }}
        job={{ ...idleJob, status: 'running' }}
        saving={false}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled();
    expect(screen.getByText('正在清理')).toBeInTheDocument();
  });
});
