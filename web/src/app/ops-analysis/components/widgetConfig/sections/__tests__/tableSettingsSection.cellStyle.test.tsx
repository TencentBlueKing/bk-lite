import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TableSettingsSection } from '../tableSettingsSection';

vi.mock('@/components/custom-table', () => ({
  default: ({ columns, dataSource }: {
    columns: Array<{
      key: string;
      render?: (...args: unknown[]) => React.ReactNode;
    }>;
    dataSource: unknown[];
  }) => (
    <div>
      {dataSource.map((record, rowIndex) => (
        <div key={rowIndex}>
          {columns.map((column) => (
            <React.Fragment key={column.key}>
              {column.render?.(undefined, record, rowIndex)}
            </React.Fragment>
          ))}
        </div>
      ))}
    </div>
  ),
}));
vi.mock('../actionInteractionModal', () => ({ ActionInteractionModal: () => null }));
vi.mock('../columnCellStyleModal', () => ({ ColumnCellStyleModal: () => null }));

afterEach(cleanup);

const renderSection = (showColumnCellStyle: boolean) =>
  render(
    <TableSettingsSection
      t={(key) => key}
      displayColumns={[
        { id: 'status', key: 'status', title: '状态', visible: true, order: 0 },
      ]}
      displayColumnOptions={[{ label: '状态', value: 'status' }]}
      actions={[]}
      filterFields={[]}
      filterFieldOptions={[]}
      showFilterFields={false}
      showColumnCellStyle={showColumnCellStyle}
      invalidConfiguredFieldKeys={[]}
      isProbingColumns={false}
      paramsChangedAfterProbe={false}
      displayColumnsError=""
      onAddFilterField={vi.fn()}
      onDeleteFilterField={vi.fn()}
      onFilterFieldChange={vi.fn()}
      onAddDisplayColumn={vi.fn()}
      onDeleteDisplayColumn={vi.fn()}
      onDisplayColumnChange={vi.fn()}
      onDisplayColumnStyleChange={vi.fn()}
      onDisplayColumnKeyBlur={vi.fn()}
      onDisplayColumnDragEnd={vi.fn()}
      onReProbeColumns={vi.fn()}
      onAddNewFilterField={vi.fn()}
      onAddNewDisplayColumn={vi.fn()}
      onActionsChange={vi.fn()}
    />,
  );

describe('TableSettingsSection cell style visibility', () => {
  it('shows the cell style entry for table', () => {
    renderSection(true);
    expect(
      screen.getByRole('button', { name: 'dashboard.columnCellStyleConfig' }),
    ).toBeTruthy();
  });

  it('hides only the cell style entry for eventTable', () => {
    renderSection(false);
    expect(
      screen.queryByRole('button', { name: 'dashboard.columnCellStyleConfig' }),
    ).toBeNull();
    expect(screen.getByDisplayValue('status')).toBeTruthy();
  });
});
