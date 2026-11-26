import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import EntityCard from '@/app/opspilot/components/entity-card';

const granted = vi.hoisted(() => ({ values: ['Edit', 'Delete'] }));

vi.mock('@/app/opspilot/components/unified-ops-card', () => ({
  default: ({ menuOverlay }: { menuOverlay: React.ReactNode }) => <div>{menuOverlay}</div>,
}));
vi.mock('@/console-layout', () => ({ useScreenAwareRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({
    hasPermission: (required: string[]) => required.every((item) => granted.values.includes(item)),
  }),
}));

const card = (showExport: boolean) => (
  <EntityCard
    id={7}
    name="助手"
    introduction="简介"
    created_by="alice"
    team_name="T1"
    team={[1]}
    permissions={['Operate']}
    showExport={showExport}
    onMenuClick={vi.fn()}
    redirectUrl="/opspilot/skill/detail"
    iconTypeMapping={['icon']}
  />
);

afterEach(() => {
  cleanup();
  granted.values = ['Edit', 'Delete'];
});

it('places export between edit and delete on an agent card', () => {
  render(card(true));
  const edit = screen.getByText('common.edit');
  const exported = screen.getByText('common.export');
  const deleted = screen.getByText('common.delete');
  expect(edit.compareDocumentPosition(exported) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(exported.compareDocumentPosition(deleted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it('keeps export off workbench cards', () => {
  render(card(false));
  expect(screen.queryByText('common.export')).toBeNull();
});

it('hides export when the edit permission is missing', () => {
  granted.values = ['Delete'];
  render(card(true));
  expect(disabledOpacity(screen.getByText('common.export'))).toBe(true);
});

function disabledOpacity(element: HTMLElement) {
  let current: HTMLElement | null = element;
  while (current) {
    if (current.style.opacity === '0.5') {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}
