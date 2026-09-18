import { fireEvent, render, renderHook, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useTableRenderer } from '../tableRenderer';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

vi.mock('@/components/group-tree-select', () => ({
  default: ({ lockedValues }: { lockedValues?: number[] }) => (
    <div data-testid="group-select" data-locked-values={JSON.stringify(lockedValues)} />
  )
}));

const ipColumn = {
  name: 'ip',
  label: 'IP address',
  type: 'input',
  required: true,
  widget_props: { placeholder: 'Enter IP address' }
};

describe('controller install table IP editing', () => {
  it('fills the node name in the same row when the IP is entered', () => {
    const row = { key: 'node-1', ip: null, node_name: null };
    const onTableDataChange = vi.fn();
    const { result } = renderHook(() => useTableRenderer());
    const column = result.current.renderTableColumn(
      ipColumn,
      [row],
      onTableDataChange
    );

    render(column.render(null, row, 0));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '10.0.0.8' }
    });

    expect(onTableDataChange).toHaveBeenCalledWith([
      {
        key: 'node-1',
        ip: '10.0.0.8',
        ip_error: null,
        node_name: '10.0.0.8',
        node_name_error: null
      }
    ]);
  });

  it('does not overwrite a user-defined node name', () => {
    const row = {
      key: 'node-1',
      ip: '10.0.0.8',
      node_name: 'production-node'
    };
    const onTableDataChange = vi.fn();
    const { result } = renderHook(() => useTableRenderer());
    const column = result.current.renderTableColumn(
      ipColumn,
      [row],
      onTableDataChange
    );

    render(column.render(null, row, 0));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '10.0.0.9' }
    });

    expect(onTableDataChange).toHaveBeenCalledWith([
      {
        key: 'node-1',
        ip: '10.0.0.9',
        ip_error: null,
        node_name: 'production-node'
      }
    ]);
  });
});

describe('controller install table organization locking', () => {
  it('locks the current organization in the organization select', () => {
    const { result } = renderHook(() => useTableRenderer([7]));
    const column = result.current.renderTableColumn(
      {
        name: 'organizations',
        label: 'Organization',
        type: 'group_select',
        required: true,
        widget_props: { placeholder: 'Select organization' }
      },
      [{ key: 'node-1', organizations: [7] }],
      vi.fn()
    );

    render(column.render(null, { key: 'node-1', organizations: [7] }, 0));

    expect(screen.getByTestId('group-select').getAttribute('data-locked-values')).toBe(
      '[7]'
    );
  });
});
