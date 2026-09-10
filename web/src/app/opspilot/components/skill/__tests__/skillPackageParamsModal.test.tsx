import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SkillPackageParamsModal, {
  listMissingRequiredParams,
  mergeDeclaredParams,
} from '../skillPackageParamsModal';
import type { SkillPackage } from '@/app/opspilot/types/skill';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal?: string) => defaultVal || key,
  }),
}));

afterEach(cleanup);

const pkg: SkillPackage = {
  id: 1,
  name: 'atuin',
  package_id: 'atuin',
  version: '1.0.0',
  variables: [
    { name: 'ATUIN_KEY', required: true, type: 'password', description: 'Atuin sync key' },
    { name: 'ATUIN_HOST', required: false, type: 'text' },
  ],
} as SkillPackage;

describe('mergeDeclaredParams', () => {
  it('seeds declared rows and keeps custom extras', () => {
    const merged = mergeDeclaredParams(pkg, [
      { key: 'ATUIN_HOST', value: 'https://example.com', type: 'text' },
      { key: 'CUSTOM_FLAG', value: '1', type: 'text' },
    ]);
    expect(merged.map((item) => item.key)).toEqual(['ATUIN_KEY', 'ATUIN_HOST', 'CUSTOM_FLAG']);
    expect(merged[0].type).toBe('password');
    expect(merged[1].value).toBe('https://example.com');
  });

  it('lists missing required declared params', () => {
    expect(listMissingRequiredParams(pkg, [{ key: 'ATUIN_HOST', value: 'x', type: 'text' }])).toEqual(['ATUIN_KEY']);
    expect(listMissingRequiredParams(pkg, [{ key: 'ATUIN_KEY', value: 'secret', type: 'password' }])).toEqual([]);
  });
});

describe('SkillPackageParamsModal', () => {
  it('renders declared names as a form, not an editable name table', () => {
    render(
      <SkillPackageParamsModal
        open
        pkg={pkg}
        items={[]}
        onCancel={vi.fn()}
        onOk={vi.fn()}
      />,
    );

    expect(screen.getByText('skill.skillPackageParams.modalTitle')).toBeTruthy();
    expect(screen.getByText('ATUIN_KEY')).toBeTruthy();
    expect(screen.getByText('ATUIN_HOST')).toBeTruthy();
    expect(screen.getByText('Atuin sync key')).toBeTruthy();
    expect(screen.getByText('还有 {count} 项必填未填')).toBeTruthy();
    expect(screen.queryByText(/SKILL.md/)).toBeNull();
    expect(screen.queryByPlaceholderText('skill.skillPackageParams.namePlaceholder')).toBeNull();
  });

  it('keeps custom variables in a separate appendix', () => {
    render(
      <SkillPackageParamsModal
        open
        pkg={pkg}
        items={[]}
        onCancel={vi.fn()}
        onOk={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /skill.skillPackageParams.add|添加变量/ }));
    expect(screen.getByPlaceholderText('skill.skillPackageParams.namePlaceholder')).toBeTruthy();
  });
});
