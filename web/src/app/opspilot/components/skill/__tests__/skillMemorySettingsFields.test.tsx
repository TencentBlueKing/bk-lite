import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Form } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import KeepMemoryOption from '../keepMemoryOption';
import SkillMemorySettingsFields from '../skillMemorySettingsFields';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('KeepMemoryOption', () => {
  it('hides the checkbox when there are no pending rounds', () => {
    render(<KeepMemoryOption pendingRounds={0} checked={false} onChange={vi.fn()} />);
    expect(screen.queryByText('skill.chat.keepMemory')).toBeNull();
  });

  it('shows the checkbox when pending rounds exist', () => {
    const onChange = vi.fn();
    render(<KeepMemoryOption pendingRounds={2} checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('SkillMemorySettingsFields', () => {
  const spaces = [
    { id: 1, name: '个人巡检', scope: 'personal' as const, default_model: '' },
    { id: 2, name: '团队知识', scope: 'team' as const, default_model: '' },
  ];

  it('lists personal spaces and hides write rounds until a space is selected', () => {
    render(
      <Form>
        <SkillMemorySettingsFields spaces={spaces} />
      </Form>
    );
    expect(screen.getByText('skill.memory.space')).toBeTruthy();
    expect(screen.queryByText('skill.memory.writeRounds')).toBeNull();
    expect(screen.getByText('chatflow.nodeConfig.addMemorySpace')).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole('combobox'));
    expect(screen.getByText('个人巡检')).toBeTruthy();
    expect(screen.queryByText('团队知识')).toBeNull();
  });

  it('shows write rounds after a memory space is selected', () => {
    render(
      <Form initialValues={{ memory_space: 1, memory_write_rounds: 10 }}>
        <SkillMemorySettingsFields spaces={spaces} />
      </Form>
    );
    expect(screen.getByText('skill.memory.writeRounds')).toBeTruthy();
    expect(screen.getByText('skill.memory.writeRoundsPrefix')).toBeTruthy();
    expect(screen.getByText('skill.memory.writeRoundsSuffix')).toBeTruthy();
  });
});
