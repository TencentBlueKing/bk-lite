'use client';
import React, { useState, useMemo } from 'react';
import { CopyTwoTone, CaretDownFilled } from '@ant-design/icons';
import { Button } from 'antd';
import CustomPopover from './customPopover';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import searchStyle from './index.module.scss';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { TableDataItem } from '@/app/log/types';
import { SearchTableProps } from '@/app/log/types/search';
import { useCopy } from '@/hooks/useCopy';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const SearchTable: React.FC<SearchTableProps> = ({
  dataSource,
  loading = false,
  scroll,
  fields = [],
  addToQuery,
  onLoadMore,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);

  const activeColumns = useMemo(() => {
    const baseColumns = [
      {
        title: 'timestamp',
        dataIndex: '_time',
        key: '_time',
        width: 160,
        fixed: 'left',
        render: (val: string) => (
          <EllipsisWithTooltip
            text={convertToLocalizedTime(val, 'YYYY-MM-DD HH:mm:ss')}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          ></EllipsisWithTooltip>
        ),
      },
      {
        title: 'message',
        dataIndex: '_msg',
        key: '_msg',
        render: (val: string) => val || '--',
        width: 800,
      },
    ];
    const storageFileds = localStorage.getItem('logSearchFields');
    const dependentFileds = storageFileds
      ? JSON.parse(storageFileds || '[]')
      : [];
    const arr = fields.length ? fields : dependentFileds;
    const activeColumns = arr
      .filter((item: string) => !['timestamp', 'message'].includes(item))
      .map((item: string) => ({
        title: item,
        dataIndex: item,
        key: item,
        width: 200,
        ellipsis: {
          showTitle: true,
        },
      }));

    return [...baseColumns, ...activeColumns];
  }, [fields]);

  const getRowExpandRender = (record: TableDataItem) => {
    return (
      <div className={`w-full ${searchStyle.detail}`}>
        <div className={searchStyle.title}>
          <div className="mb-1">
            <CopyTwoTone
              className="cursor-pointer mr-[4px]"
              onClick={() => copy(record._msg)}
            />
            <span className="font-[500] break-all">{record._msg}</span>
          </div>
          <div>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">
                {t('common.time')}：
              </span>
              <span>
                {convertToLocalizedTime(
                  record._time,
                  'YYYY-MM-DD HH:mm:ss.SSS'
                )}
              </span>
            </span>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">
                {t('log.integration.collector')}：
              </span>
              <span>{record.collector || '--'}</span>
            </span>
            <span>
              <span className="text-[var(--color-text-3)]">
                {t('log.integration.collectType')}：
              </span>
              <span>{record.collect_type || '--'}</span>
            </span>
          </div>
        </div>
        <ul>
          {Object.entries(record)
            .map(([key, value]) => ({
              label: key,
              value,
            }))
            .filter((item) => item.label !== 'id')
            .map((item: TableDataItem, index: number) => (
              <li className="flex items-start mt-[10px]" key={index}>
                <div className="flex items-center min-w-[250px] w-[250px] mr-[10px]">
                  <CustomPopover
                    title={item.label}
                    content={(onClose) => (
                      <ul>
                        <li>
                          <Button
                            type="link"
                            size="small"
                            onClick={() => {
                              onClose();
                              addToQuery(item, 'field');
                            }}
                          >
                            {t('log.search.addToQuery')}
                          </Button>
                        </li>
                      </ul>
                    )}
                  >
                    <div
                      className={`flex max-w-[100%] cursor-pointer ${searchStyle.field}`}
                    >
                      <EllipsisWithTooltip
                        text={item.label}
                        className="w-full overflow-hidden text-[var(--color-text-3)] text-ellipsis whitespace-nowrap"
                      ></EllipsisWithTooltip>
                      <span className="text-[var(--color-text-3)]">:</span>
                      <CaretDownFilled
                        className={`text-[12px] ${searchStyle.arrow}`}
                      />
                    </div>
                  </CustomPopover>
                </div>
                <span className={`${searchStyle.value}`}>
                  <CustomPopover
                    title={`${item.label} = ${item.value}`}
                    content={(onClose) => (
                      <ul>
                        <li>
                          <Button
                            type="link"
                            size="small"
                            onClick={() => {
                              onClose();
                              addToQuery(item, 'value');
                            }}
                          >
                            {t('log.search.addToQuery')}
                          </Button>
                        </li>
                      </ul>
                    )}
                  >
                    <span className="break-all">{item.value}</span>
                    <CaretDownFilled
                      className={`text-[12px] ${searchStyle.arrow}`}
                    />
                  </CustomPopover>
                </span>
              </li>
            ))}
        </ul>
      </div>
    );
  };

  return (
    <CustomTable
      className="w-[calc(100vw-250px)] min-w-[1030px]"
      columns={activeColumns}
      dataSource={dataSource}
      loading={loading}
      virtual
      rowKey="id"
      scroll={scroll || undefined}
      expandable={{
        columnWidth: 36,
        expandedRowRender: (record) => getRowExpandRender(record),
        expandedRowKeys: expandedRowKeys,
        onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as React.Key[]),
      }}
      onScroll={(e: any) => {
        const { scrollTop, scrollHeight, clientHeight } = e.target;
        if (scrollTop + clientHeight + 10 >= scrollHeight) {
          onLoadMore?.();
        }
      }}
    />
  );
};

export default SearchTable;
