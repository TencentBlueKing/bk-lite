import React, { useMemo, useState } from 'react';
import { Pagination } from 'antd';
import CustomTable from '@/components/custom-table';
import { TABLE_PAGE_SIZE, type ScanHitItem } from './scanHits';

const ScanUnmatchedGroupTable: React.FC<{
  columns: Array<Record<string, unknown>>;
  hits: ScanHitItem[];
  selectedHitIds: number[];
  onSelectedChange: (nextIds: number[], visibleIds: number[]) => void;
}> = ({ columns, hits, selectedHitIds, onSelectedChange }) => {
  const [page, setPage] = useState(1);
  const pagedHits = useMemo(() => {
    const start = (page - 1) * TABLE_PAGE_SIZE;
    return hits.slice(start, start + TABLE_PAGE_SIZE);
  }, [hits, page]);

  return (
    <div>
      <CustomTable
        rowKey="id"
        columns={columns}
        dataSource={pagedHits}
        rowSelection={{
          selectedRowKeys: selectedHitIds,
          onChange: (keys) =>
            onSelectedChange(
              keys as number[],
              pagedHits.map((item) => item.id)
            ),
        }}
        pagination={false}
      />
      {hits.length > TABLE_PAGE_SIZE ? (
        <div className="flex justify-end p-2.5">
          <Pagination
            size="small"
            current={page}
            pageSize={TABLE_PAGE_SIZE}
            total={hits.length}
            showSizeChanger={false}
            onChange={(next) => setPage(next)}
          />
        </div>
      ) : null}
    </div>
  );
};

export default ScanUnmatchedGroupTable;
