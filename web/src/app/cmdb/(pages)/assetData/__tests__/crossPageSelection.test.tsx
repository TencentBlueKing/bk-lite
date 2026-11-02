import React, { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { Table } from 'antd';
import { expect, it } from 'vitest';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: () => ({ matches: false, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined }),
});

const pages = [
  Array.from({ length: 10 }, (_, index) => ({ inst_uuid: `page-1-${index}` })),
  [{ inst_uuid: 'page-2-0' }],
];

function selectedKeys() {
  return (screen.getByRole('status').textContent ?? '').split(',').filter(Boolean);
}

function AssetSelection() {
  const [page, setPage] = useState(0);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  return (
    <div>
      <button type="button" onClick={() => setPage(1)}>next</button>
      <output>{selectedRowKeys.join(',')}</output>
      <Table
        rowKey="inst_uuid"
        pagination={false}
        dataSource={pages[page]}
        columns={[{ title: 'id', dataIndex: 'inst_uuid' }]}
        rowSelection={{
          selectedRowKeys,
          preserveSelectedRowKeys: true,
          onChange: setSelectedRowKeys,
        }}
      />
    </div>
  );
}

it('keeps the previous page selection when another page is checked', async () => {
  render(<AssetSelection />);

  await act(async () => {
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
  });
  expect(selectedKeys()).toHaveLength(10);

  fireEvent.click(screen.getByRole('button', { name: 'next' }));
  const pageTwoBoxes = screen.getAllByRole('checkbox');
  await act(async () => {
    fireEvent.click(pageTwoBoxes[pageTwoBoxes.length - 1]);
  });

  const selected = selectedKeys();
  expect(selected).toHaveLength(11);
  expect(selected).toContain('page-1-0');
  expect(selected).toContain('page-2-0');
});
