'use client';

import React from 'react';
import { Pagination, Table } from 'antd';
import { DownOutlined, UpOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import type { AttrFieldType, ColumnItem, UserItem } from '@/app/cmdb/types/assetManage';
import ModelAttrSearch from './modelAttrSearch';
import type { ModelSearchPreference } from './tagViewSearchPreference';

export const PAGE_SIZE_OPTIONS = ['10', '20', '50', '100'];

interface ModelResultSectionProps {
  modelId: string;
  title: string;
  count: number;
  columns: ColumnItem[];
  insts: Array<Record<string, unknown>>;
  page: number;
  pageSize: number;
  attrList: AttrFieldType[];
  userList: UserItem[];
  proxyOptions: Array<{ proxy_id: string; proxy_name: string }>;
  searchPreference?: ModelSearchPreference;
  collapsed: boolean;
  loading: boolean;
  onToggle: () => void;
  onPageChange: (page: number, pageSize: number) => void;
  onSearch: (preference: ModelSearchPreference) => void;
}

const iconStateClass = (active: boolean) =>
  [
    'absolute inset-0 flex items-center justify-center',
    'transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]',
    active
      ? 'scale-100 opacity-100 blur-0'
      : 'scale-[0.25] opacity-0 blur-[4px]',
  ].join(' ');

const ModelResultSection: React.FC<ModelResultSectionProps> = ({
  modelId,
  title,
  count,
  columns,
  insts,
  page,
  pageSize,
  attrList,
  userList,
  proxyOptions,
  searchPreference,
  collapsed,
  loading,
  onToggle,
  onPageChange,
  onSearch,
}) => {
  const { t } = useTranslation();
  const panelId = `tag-view-model-${modelId}`;

  return (
    <section
      id={panelId}
      className="mb-4 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="m-0 truncate text-[13px] font-semibold text-[var(--color-text-1)]">
            {title}
          </h2>
          {count > 0 && (
            <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
              {count}
            </span>
          )}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <ModelAttrSearch
            attrList={attrList}
            userList={userList}
            proxyOptions={proxyOptions}
            preference={searchPreference}
            onCommit={onSearch}
          />
          <button
            type="button"
            aria-expanded={!collapsed}
            aria-controls={`${panelId}-body`}
            aria-label={collapsed ? t('SceneView.expand') : t('SceneView.collapse')}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] focus-visible:outline focus-visible:outline-offset-2"
            onClick={onToggle}
          >
            <span className="relative inline-flex h-4 w-4 items-center justify-center">
              <span className={iconStateClass(collapsed)}>
                <DownOutlined />
              </span>
              <span
                className={[
                  'transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]',
                  collapsed
                    ? 'scale-[0.25] opacity-0 blur-[4px]'
                    : 'scale-100 opacity-100 blur-0',
                ].join(' ')}
              >
                <UpOutlined />
              </span>
            </span>
          </button>
        </div>
      </div>
      {!collapsed && (
        <div id={`${panelId}-body`} className="p-0">
          <Table
            size="small"
            loading={loading}
            rowKey={(row, index) =>
              String(resolveCmdbInstUuid(row.inst_uuid) || `${modelId}-${index}`)
            }
            columns={columns}
            dataSource={insts}
            pagination={false}
            scroll={{ x: 'max-content' }}
          />
          <div className="flex justify-end px-3.5 py-3">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={count}
              showSizeChanger
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              showTotal={(value) => t('SceneView.pageTotal', '', { total: value })}
              onChange={onPageChange}
            />
          </div>
        </div>
      )}
    </section>
  );
};

export default ModelResultSection;
