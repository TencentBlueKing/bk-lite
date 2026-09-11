import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OpsPilotEntityDetailIntro from '../index';

vi.mock('@/components/icon', () => ({
  default: ({ type, className }: { type: string; className?: string }) => (
    <span data-testid={`icon-${type}`} className={className} />
  ),
}));

describe('OpsPilotEntityDetailIntro', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders name, description and aligned icon without background container', () => {
    render(
      <OpsPilotEntityDetailIntro
        name="测试应用"
        description="这是一个测试应用的详细描述"
        iconType="gongzuotai"
      />
    );

    expect(screen.getByText('测试应用')).toBeTruthy();
    expect(screen.getByText('这是一个测试应用的详细描述')).toBeTruthy();

    const icon = screen.getByTestId('icon-gongzuotai');
    expect(icon).toBeTruthy();
    expect(icon.className).toContain('text-base');
    expect(icon.className).toContain('text-[var(--color-primary)]');
  });

  it('renders fallback title and empty intro text when name and description are missing', () => {
    render(
      <OpsPilotEntityDetailIntro
        iconType="zhishiku1"
        fallbackTitle="默认知识库"
        emptyIntroText="暂无知识库简介"
      />
    );

    expect(screen.getByText('默认知识库')).toBeTruthy();
    expect(screen.getByText('暂无知识库简介')).toBeTruthy();
  });
});
