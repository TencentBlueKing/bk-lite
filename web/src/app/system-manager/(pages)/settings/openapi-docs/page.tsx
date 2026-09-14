'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Spin, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import HttpMethodBadge from '@/components/http-method-badge';
import TopSection from '@/components/top-section';
import { useSettingsApi } from '@/app/system-manager/api/settings';
import {
  filterOpenApiRows,
  flattenOpenApiCatalog,
  formatAuthHeaderPlainText,
  injectDescriptionKey,
  OPENAPI_GATEWAY_PREFIX,
  type OpenAPIDocRow,
} from '@/app/system-manager/utils/openapiDocs';
import { exportOpenApiDocsToPdf } from '@/app/system-manager/utils/exportOpenApiDocsPdf';
import { useTranslation } from '@/utils/i18n';
import OpenApiDocsDetail from './OpenApiDocsDetail';
import OpenApiDocsToolbar from './OpenApiDocsToolbar';

const renderMethodBadge = (method: string, kind: OpenAPIDocRow['kind']) => {
  if (kind === 'external') {
    return (
      <Tag className="m-0 inline-flex h-[22px] w-[52px] items-center justify-center font-mono text-[11px] font-semibold">
        EXT
      </Tag>
    );
  }
  return (
    <HttpMethodBadge
      method={method}
      className="w-[52px] shrink-0 justify-center font-mono text-[11px] font-semibold tracking-wide select-none"
    />
  );
};

const formatSummary = (rawSummary: string, kind: OpenAPIDocRow['kind'], fallback: string) => {
  const summary = rawSummary || (kind === 'external' ? fallback : '--');
  const match = summary.match(/^([^(（]+)[(（]([^)）]+)[)）]?$/);
  if (match) {
    const title = match[1].trim();
    const note = match[2].trim();
    return { title, note, full: summary };
  }
  return { title: summary, note: '', full: summary };
};

const TABLE_SCROLL_Y = 'calc(100vh - 455px)';

const OpenApiDocsPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchOpenApiDocs } = useSettingsApi();
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [serviceFilter, setServiceFilter] = useState<string>('all');
  const [methodFilter, setMethodFilter] = useState<string>('ALL');
  const [kindFilter, setKindFilter] = useState<string>('all');
  const [rows, setRows] = useState<OpenAPIDocRow[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('');
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [activeDetailTab, setActiveDetailTab] = useState<string>('params');
  const [exporting, setExporting] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const catalog = await fetchOpenApiDocs();
      setRows(flattenOpenApiCatalog(catalog));
    } catch {
      message.error(t('common.fetchFailed'));
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const serviceOptions = useMemo(() => {
    const services = Array.from(new Set(rows.map((row) => row.service))).sort();
    return [
      { label: t('system.settings.openapiDocs.allServices'), value: 'all' },
      ...services.map((srv) => ({ label: srv, value: srv })),
    ];
  }, [rows, t]);

  const methodOptions = useMemo(() => {
    const methods = Array.from(
      new Set(rows.map((row) => row.method.toUpperCase()).filter(Boolean))
    ).sort();
    return [
      { label: t('system.settings.openapiDocs.allMethods'), value: 'ALL' },
      ...methods.map((m) => ({ label: m, value: m })),
    ];
  }, [rows, t]);

  const kindOptions = useMemo(
    () => [
      { label: t('system.settings.openapiDocs.allKinds'), value: 'all' },
      { label: t('system.settings.openapiDocs.internal'), value: 'internal' },
      { label: t('system.settings.openapiDocs.external'), value: 'external' },
    ],
    [t]
  );

  const filteredRows = useMemo(
    () =>
      filterOpenApiRows(rows, {
        query,
        service: serviceFilter,
        method: methodFilter,
        kind: kindFilter,
      }),
    [rows, query, serviceFilter, methodFilter, kindFilter]
  );

  useEffect(() => {
    setPagination((prev) => ({ ...prev, current: 1, total: filteredRows.length }));
  }, [filteredRows.length, query, serviceFilter, methodFilter, kindFilter]);

  const pagedRows = useMemo(() => {
    const start = (pagination.current - 1) * pagination.pageSize;
    return filteredRows.slice(start, start + pagination.pageSize);
  }, [filteredRows, pagination.current, pagination.pageSize]);

  useEffect(() => {
    if (!pagedRows.length) {
      setSelectedKey('');
      return;
    }
    if (!pagedRows.some((row) => row.key === selectedKey)) {
      setSelectedKey(pagedRows[0].key);
    }
  }, [pagedRows, selectedKey]);

  const selectedRow = useMemo(
    () => filteredRows.find((row) => row.key === selectedKey),
    [filteredRows, selectedKey]
  );

  const handleResetFilters = () => {
    setQuery('');
    setServiceFilter('all');
    setMethodFilter('ALL');
    setKindFilter('all');
  };

  const handleExportPdf = async () => {
    if (!filteredRows.length) {
      message.warning(t('system.settings.openapiDocs.empty'));
      return;
    }
    setExporting(true);
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => resolve());
      });
    });
    try {
      await exportOpenApiDocsToPdf(filteredRows, {
        title: t('system.settings.openapiDocs.title'),
        catalog: t('system.settings.openapiDocs.catalog'),
        generatedAt: new Date().toLocaleString(),
        totalCount: t('system.settings.openapiDocs.totalCount', undefined, {
          count: filteredRows.length,
        }),
        kind: t('system.settings.openapiDocs.kind'),
        authHeader: t('system.settings.openapiDocs.authHeader'),
        authHeaderDesc: formatAuthHeaderPlainText(
          t('system.settings.openapiDocs.authHeaderDesc'),
          t('system.settings.openapiDocs.authHeaderKeyHint'),
          t('system.settings.openapiDocs.authHeaderKeyPath'),
        ),
        internal: t('system.settings.openapiDocs.internal'),
        external: t('system.settings.openapiDocs.external'),
        service: t('system.settings.openapiDocs.service'),
        method: t('system.settings.openapiDocs.method'),
        path: t('system.settings.openapiDocs.path'),
        summary: t('system.settings.openapiDocs.summary'),
        fieldName: t('system.settings.openapiDocs.fieldName'),
        fieldType: t('system.settings.openapiDocs.fieldType'),
        required: t('system.settings.openapiDocs.required'),
        range: t('system.settings.openapiDocs.range'),
        default: t('system.settings.openapiDocs.default'),
        choices: t('system.settings.openapiDocs.choices'),
        yes: t('system.settings.openapiDocs.yes'),
        no: t('system.settings.openapiDocs.no'),
        noParams: t('system.settings.openapiDocs.noParams'),
        entryPrefix: t('system.settings.openapiDocs.entryPrefix'),
        docUrl: t('system.settings.openapiDocs.docUrl'),
        noDocUrl: t('system.settings.openapiDocs.noDocUrl'),
        externalDocHint: t('system.settings.openapiDocs.externalDocHint'),
        permissionControl: t('system.settings.openapiDocs.permissionControl'),
        unrestricted: t('system.settings.openapiDocs.unrestricted'),
        orgScope: t('system.settings.openapiDocs.orgScope'),
        tabExample: t('system.settings.openapiDocs.tabExample'),
        inject: (value) => t(injectDescriptionKey(value)),
      });
      message.success(t('common.exportSuccess'));
    } catch {
      message.error(t('common.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const hasActiveFilters =
    Boolean(query) || serviceFilter !== 'all' || methodFilter !== 'ALL' || kindFilter !== 'all';

  const columns: ColumnsType<OpenAPIDocRow> = [
    {
      title: t('system.settings.openapiDocs.method'),
      dataIndex: 'method',
      key: 'method',
      width: 80,
      render: (method: string, row) => (
        <div className="relative flex items-center pl-1">
          {row.key === selectedKey ? (
            <span className="absolute -left-2 top-0.5 bottom-0.5 w-[3px] rounded-r bg-[var(--color-primary)]" />
          ) : null}
          {renderMethodBadge(method, row.kind)}
        </div>
      ),
    },
    {
      title: t('system.settings.openapiDocs.path'),
      dataIndex: 'path',
      key: 'path',
      width: 280,
      ellipsis: { showTitle: false },
      render: (path: string) => {
        const prefix = OPENAPI_GATEWAY_PREFIX;
        const hasPrefix = path.startsWith(prefix);
        const subPath = hasPrefix ? path.slice(prefix.length) : path;
        return (
          <div className="flex min-w-0 w-full items-center overflow-hidden font-mono text-xs">
            {hasPrefix ? (
              <span className="shrink-0 select-none text-[11px] text-[var(--color-text-4)]">
                {prefix}
              </span>
            ) : null}
            <EllipsisWithTooltip
              text={subPath}
              tooltip={path}
              className="min-w-0 flex-1 truncate font-medium text-[var(--color-text-1)] group-hover:text-[var(--color-primary)]"
              getPopupContainer={() => document.body}
            />
          </div>
        );
      },
    },
    {
      title: t('system.settings.openapiDocs.service'),
      dataIndex: 'service',
      key: 'service',
      width: 110,
      ellipsis: true,
      render: (service: string) => (
        <Tag className="m-0 font-mono text-xs">
          {service}
        </Tag>
      ),
    },
    {
      title: t('system.settings.openapiDocs.summary'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: { showTitle: false },
      render: (summary: string, row) => {
        const { title, note, full } = formatSummary(
          summary,
          row.kind,
          t('system.settings.openapiDocs.external')
        );
        const node = (
          <>
            <span className="text-[var(--color-text-1)]">{title}</span>
            {note ? (
              <span className="ml-1 text-[11px] text-[var(--color-text-3)]">
                ({note})
              </span>
            ) : null}
          </>
        );
        return (
          <EllipsisWithTooltip
            text={node}
            tooltip={full}
            className="w-full truncate text-xs"
            getPopupContainer={() => document.body}
          />
        );
      },
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div>
        <TopSection
          title={t('system.settings.openapiDocs.title')}
          content={t('system.settings.openapiDocs.content')}
        />
      </div>

      <section className="flex h-[calc(100vh-235px)] flex-col rounded-md bg-[var(--color-bg)] p-4">
        <OpenApiDocsToolbar
          query={query}
          onQueryChange={setQuery}
          serviceFilter={serviceFilter}
          onServiceFilterChange={setServiceFilter}
          methodFilter={methodFilter}
          onMethodFilterChange={setMethodFilter}
          kindFilter={kindFilter}
          onKindFilterChange={setKindFilter}
          serviceOptions={serviceOptions}
          methodOptions={methodOptions}
          kindOptions={kindOptions}
          hasActiveFilters={hasActiveFilters}
          onResetFilters={handleResetFilters}
          exporting={exporting}
          loading={loading}
          filteredCount={filteredRows.length}
          onExport={() => void handleExportPdf()}
          onRefresh={() => void loadData()}
        />

        <div className="flex min-h-0 flex-1 gap-4">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] p-2">
            <div className="min-h-0 flex-1">
              <Spin
                spinning={loading || exporting}
                tip={exporting ? t('system.settings.openapiDocs.exportingPdf') : undefined}
              >
                <CustomTable<OpenAPIDocRow>
                  rowKey="key"
                  size="small"
                  columns={columns}
                  dataSource={pagedRows}
                  autoScrollX={false}
                  scroll={{ y: TABLE_SCROLL_Y }}
                  pagination={{
                    current: pagination.current,
                    pageSize: pagination.pageSize,
                    total: filteredRows.length,
                    showSizeChanger: true,
                    pageSizeOptions: ['10', '20', '50', '100'],
                    onChange: (page, pageSize) => {
                      const targetPage = pageSize === pagination.pageSize ? page : 1;
                      setPagination({ current: targetPage, pageSize, total: filteredRows.length });
                    },
                  }}
                  locale={{
                    emptyText: (
                      <CompactEmptyState description={t('system.settings.openapiDocs.empty')} />
                    ),
                  }}
                  rowClassName={(row) =>
                    `group cursor-pointer transition-colors ${
                      row.key === selectedKey
                        ? '!bg-[var(--color-primary-bg-active)]'
                        : 'hover:bg-[var(--color-fill-1)]'
                    }`
                  }
                  onRow={(row) => ({
                    onClick: () => setSelectedKey(row.key),
                  })}
                />
              </Spin>
            </div>
          </div>

          <OpenApiDocsDetail
            selectedRow={selectedRow}
            activeTab={activeDetailTab}
            onTabChange={setActiveDetailTab}
          />
        </div>
      </section>
    </div>
  );
};

export default OpenApiDocsPage;
