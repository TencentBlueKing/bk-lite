'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, Empty, Input, Select } from 'antd';
import type { TableRowSelection } from 'antd/es/table/interface';
import { SearchOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import type { BindingSearchHit, BindingSearchPage, ModelOption } from '../binding/model';
import { bindingModelLabel, bindingSearchMode } from '../binding/model';

export interface ResourcePickerProps {
  active: boolean;
  models: ModelOption[];
  initialModelId?: string;
  mode: 'multiple' | 'single';
  disabledUuids: ReadonlySet<string>;
  selected: BindingSearchHit[];
  onSelectedChange: (hits: BindingSearchHit[]) => void;
  onSearch: (
    keyword: string,
    modelId: string,
    page: number,
    pageSize: number,
  ) => Promise<BindingSearchPage>;
  scrollY: string;
}

const PAGE_SIZE = 20;

const ResourcePicker = ({
  active,
  models,
  initialModelId = '',
  mode,
  disabledUuids,
  selected,
  onSelectedChange,
  onSearch,
  scrollY,
}: ResourcePickerProps) => {
  const { t } = useTranslation();
  const [keyword, setKeyword] = useState('');
  const [modelId, setModelId] = useState(initialModelId);
  const [hits, setHits] = useState<BindingSearchHit[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const searchSeqRef = useRef(0);

  useEffect(() => {
    if (!active) return;
    setKeyword('');
    setModelId(initialModelId);
    setPage(1);
    setPageSize(PAGE_SIZE);
  }, [active, initialModelId]);

  useEffect(() => {
    searchSeqRef.current += 1;
    const seq = searchSeqRef.current;
    if (!active || bindingSearchMode(keyword, modelId) === 'idle') {
      setHits([]);
      setTotal(0);
      setLoading(false);
      setFailed(false);
      return undefined;
    }
    setLoading(true);
    setFailed(false);
    const timer = window.setTimeout(() => {
      onSearch(keyword.trim(), modelId, page, pageSize)
        .then((result) => {
          if (seq !== searchSeqRef.current) return;
          setHits(result.hits);
          setTotal(result.total);
          setLoading(false);
        })
        .catch(() => {
          if (seq !== searchSeqRef.current) return;
          setHits([]);
          setTotal(0);
          setLoading(false);
          setFailed(true);
        });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [active, keyword, modelId, onSearch, page, pageSize, retryToken]);

  const changeKeyword = (value: string) => {
    setKeyword(value);
    setPage(1);
  };

  const changeModel = (value: string) => {
    setModelId(value);
    setPage(1);
  };

  const changePage = (nextPage: number, nextSize: number) => {
    setPage(nextSize === pageSize ? nextPage : 1);
    setPageSize(nextSize);
  };

  const selectable = selected.filter((hit) => !disabledUuids.has(hit.inst_uuid));
  const idle = bindingSearchMode(keyword, modelId) === 'idle';

  const rowSelection: TableRowSelection<BindingSearchHit> = {
    type: mode === 'single' ? 'radio' : 'checkbox',
    selectedRowKeys: selectable.map((hit) => hit.inst_uuid),
    preserveSelectedRowKeys: true,
    getCheckboxProps: (record) => ({ disabled: disabledUuids.has(record.inst_uuid) }),
    onSelect: (record, checked) => {
      if (disabledUuids.has(record.inst_uuid)) return;
      if (mode === 'single') {
        onSelectedChange(checked ? [record] : []);
        return;
      }
      onSelectedChange(
        checked
          ? [...selected, record]
          : selected.filter((item) => item.inst_uuid !== record.inst_uuid),
      );
    },
    onSelectAll: (checked, _rows, changeRows) => {
      if (mode !== 'multiple') return;
      if (!checked) {
        const drop = new Set(changeRows.map((row) => row.inst_uuid));
        onSelectedChange(selected.filter((item) => !drop.has(item.inst_uuid)));
        return;
      }
      const seen = new Set(selected.map((item) => item.inst_uuid));
      const added = changeRows.filter((row) => (
        !disabledUuids.has(row.inst_uuid) && !seen.has(row.inst_uuid)
      ));
      onSelectedChange([...selected, ...added]);
    },
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col" data-testid="architecture-resource-picker">
      <div className="mb-3 flex shrink-0 gap-2">
        <Select
          allowClear
          showSearch
          className="w-[280px] shrink-0"
          optionFilterProp="label"
          placeholder={t('opsAnalysis.architecture.bindingModel')}
          value={modelId || undefined}
          options={models.map((model) => ({
            value: model.model_id,
            label: model.model_name,
          }))}
          onChange={(value) => changeModel(value || '')}
        />
        <Input
          allowClear
          prefix={<SearchOutlined className="text-[var(--color-text-4)]" />}
          placeholder={t('opsAnalysis.architecture.bindingSearch')}
          value={keyword}
          onChange={(event) => changeKeyword(event.target.value)}
        />
      </div>
      <div className="min-h-0 flex-1" data-testid="architecture-binding-results">
        <CustomTable<BindingSearchHit>
          size="small"
          rowKey="inst_uuid"
          dataSource={idle || failed ? [] : hits}
          loading={loading && !idle}
          scroll={{ y: scrollY }}
          rowSelection={rowSelection}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  failed
                    ? t('opsAnalysis.architecture.bindingSearchFailed')
                    : idle
                      ? t('opsAnalysis.architecture.bindingIdle')
                      : t('common.noData')
                }
              >
                {failed ? (
                  <Button type="link" size="small" onClick={() => setRetryToken((current) => current + 1)}>
                    {t('opsAnalysis.architecture.bindingSearchRetry')}
                  </Button>
                ) : null}
              </Empty>
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total: idle || failed ? 0 : total,
            showSizeChanger: true,
            onChange: changePage,
          }}
          columns={[
            {
              title: t('common.name'),
              dataIndex: 'inst_name',
              ellipsis: true,
              render: (name: string, record) => name || record.inst_uuid,
            },
            {
              title: t('opsAnalysis.architecture.bindingModel'),
              dataIndex: 'model_id',
              width: 160,
              ellipsis: true,
              render: (id: string) => bindingModelLabel(models, id),
            },
            {
              title: 'IP',
              dataIndex: 'ip_addr',
              width: 160,
              ellipsis: true,
              render: (ip: string) => ip || '--',
            },
          ]}
        />
      </div>
    </div>
  );
};

export default ResourcePicker;
