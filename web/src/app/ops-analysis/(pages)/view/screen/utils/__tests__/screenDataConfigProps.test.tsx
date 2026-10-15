import React, { memo, useState } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { areScreenDataConfigPropsEqual } from '../screenDataConfigProps';

afterEach(cleanup);

const item = { i: 'new' };
const dataSources: unknown[] = [];

const Panel = memo(function Panel({
  dataSourceManager,
}: {
  item: unknown;
  dataSourceManager: {
    dataSources: unknown;
    dataSourcesLoading: boolean;
    selectedDataSource?: { name: string };
  };
}) {
  return (
    <span data-testid="source-name">
      {dataSourceManager.selectedDataSource?.name || ''}
    </span>
  );
}, areScreenDataConfigPropsEqual);

function Host() {
  const [selectedDataSource, setSelectedDataSource] = useState<
    { name: string } | undefined
  >(undefined);
  return (
    <>
      <button
        type="button"
        onClick={() =>
          setSelectedDataSource({ name: 'CMDB 模型实例明细' })
        }
      >
        select
      </button>
      <Panel
        item={item}
        dataSourceManager={{
          dataSources,
          dataSourcesLoading: false,
          selectedDataSource,
        }}
      />
    </>
  );
}

describe('screen data config props', () => {
  it('shows the selected data source after the manager updates it', async () => {
    const user = userEvent.setup();
    render(<Host />);

    expect(screen.getByTestId('source-name').textContent).toBe('');
    await user.click(screen.getByRole('button', { name: 'select' }));

    expect(screen.getByTestId('source-name').textContent).toBe(
      'CMDB 模型实例明细',
    );
  });
});
