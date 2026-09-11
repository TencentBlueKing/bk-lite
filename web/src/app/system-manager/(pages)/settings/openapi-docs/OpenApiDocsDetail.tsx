'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import { Button, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  CopyOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import CodeSnippet from '@/components/code-snippet';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import HttpEndpointDisplay from '@/components/http-endpoint-display';
import SourceOriginBadge from '@/components/source-origin-badge';
import { useCopy } from '@/hooks/useCopy';
import type { OpenAPIFieldSpec } from '@/app/system-manager/api/settings';
import {
  fieldHasRange,
  formatChoicesDisplay,
  formatFieldRange,
  generateCurlCommand,
  generateSamplePayload,
  injectDescriptionKey,
  OPENAPI_SECRET_KEY_HREF,
  splitLinkPlaceholder,
  type OpenAPIDocRow,
} from '@/app/system-manager/utils/openapiDocs';
import { useTranslation } from '@/utils/i18n';

interface OpenApiDocsDetailProps {
  selectedRow?: OpenAPIDocRow;
  activeTab: string;
  onTabChange: (key: string) => void;
}

const OpenApiDocsDetail: React.FC<OpenApiDocsDetailProps> = ({
  selectedRow,
  activeTab,
  onTabChange,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  const schemaRows = useMemo(() => {
    if (!selectedRow?.requestSchema) return [];
    return Object.entries(selectedRow.requestSchema).map(([name, spec]) => ({
      name,
      ...spec,
    }));
  }, [selectedRow]);

  const schemaColumns = useMemo(() => {
    const columns: ColumnsType<{ name: string } & OpenAPIFieldSpec> = [
      {
        title: t('system.settings.openapiDocs.fieldName'),
        dataIndex: 'name',
        key: 'name',
        width: 130,
        render: (name: string, record) => (
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs font-semibold text-[var(--color-text-1)]">{name}</span>
            {record.required && (
              <span className="text-[10px] font-bold leading-none text-[var(--color-fail)]">*</span>
            )}
          </div>
        ),
      },
      {
        title: t('system.settings.openapiDocs.fieldType'),
        dataIndex: 'type',
        key: 'type',
        width: 90,
        render: (type: string) => (
          <Tag className="m-0 border-0 bg-[var(--color-fill-2)] font-mono text-[11px] text-[var(--color-text-2)]">
            {type}
          </Tag>
        ),
      },
      {
        title: t('system.settings.openapiDocs.required'),
        dataIndex: 'required',
        key: 'required',
        width: 65,
        render: (required: boolean) =>
          required ? (
            <span className="text-xs font-medium text-[var(--color-fail)]">
              {t('system.settings.openapiDocs.yes')}
            </span>
          ) : (
            <span className="text-xs text-[var(--color-text-3)]">{t('system.settings.openapiDocs.no')}</span>
          ),
      },
    ];

    if (schemaRows.some((row) => fieldHasRange(row))) {
      columns.push({
        title: t('system.settings.openapiDocs.range'),
        key: 'range',
        width: 110,
        render: (_, record) => (
          <span className="font-mono text-xs text-[var(--color-text-3)]">
            {formatFieldRange(record.min_value, record.max_value) || '--'}
          </span>
        ),
      });
    }

    columns.push(
      {
        title: t('system.settings.openapiDocs.default'),
        dataIndex: 'default',
        key: 'default',
        width: 80,
        ellipsis: true,
        render: (value: unknown) => (
          <EllipsisWithTooltip
            text={value == null ? '--' : String(value)}
            className="w-full truncate font-mono text-xs text-[var(--color-text-3)]"
          />
        ),
      },
      {
        title: t('system.settings.openapiDocs.choices'),
        dataIndex: 'choices',
        key: 'choices',
        ellipsis: true,
        render: (choices: unknown) => (
          <EllipsisWithTooltip
            text={formatChoicesDisplay(choices)}
            className="w-full truncate text-xs text-[var(--color-text-3)]"
          />
        ),
      },
    );

    return columns;
  }, [schemaRows, t]);

  const samplePayload = useMemo(() => {
    if (!selectedRow?.requestSchema) return null;
    return generateSamplePayload(selectedRow.requestSchema);
  }, [selectedRow]);

  const curlCommand = useMemo(() => {
    if (!selectedRow || selectedRow.kind === 'external') return '';
    return generateCurlCommand(selectedRow);
  }, [selectedRow]);

  const [authKeyHintBefore, authKeyHintAfter] = splitLinkPlaceholder(
    t('system.settings.openapiDocs.authHeaderKeyHint'),
  );

  return (
    <aside className="flex w-[min(32rem,44%)] shrink-0 flex-col overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)]">
      {!selectedRow ? (
        <div className="flex h-full items-center justify-center p-8">
          <CompactEmptyState description={t('system.settings.openapiDocs.selectRow')} />
        </div>
      ) : (
        <div className="flex h-full flex-col overflow-hidden">
          <div className="border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Tag className="m-0 font-mono text-xs">
                {selectedRow.service}
              </Tag>
              <SourceOriginBadge
                kind={selectedRow.kind === 'internal' ? 'builtin' : 'external'}
                label={
                  selectedRow.kind === 'internal'
                    ? t('system.settings.openapiDocs.internal')
                    : t('system.settings.openapiDocs.external')
                }
              />
            </div>

            <div className="mt-2.5">
              {selectedRow.kind === 'external' ? (
                <div className="flex items-center gap-2 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 py-1.5">
                  <span className="min-w-0 flex-1 break-all font-mono text-xs font-semibold text-[var(--color-primary)]">
                    {selectedRow.path}
                  </span>
                  <Button
                    type="text"
                    size="small"
                    icon={<CopyOutlined />}
                    aria-label={t('system.settings.openapiDocs.copyPath')}
                    onClick={() => copy(selectedRow.path)}
                  />
                </div>
              ) : (
                <HttpEndpointDisplay
                  method={selectedRow.method}
                  endpoint={selectedRow.path}
                  className="border-[var(--color-border-1)] bg-[var(--color-bg)]"
                  endpointClassName="text-xs"
                />
              )}
            </div>

            {selectedRow.summary ? (
              <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-2)]">
                {selectedRow.summary}
              </p>
            ) : null}
          </div>

          <div className="flex-1 overflow-auto p-4">
            {selectedRow.kind === 'external' ? (
              <div className="space-y-4">
                <p className="text-xs leading-relaxed text-[var(--color-text-2)]">
                  {t('system.settings.openapiDocs.externalDocHint')}
                </p>
                <div>
                  <div className="mb-1 text-xs font-medium text-[var(--color-text-2)]">
                    {t('system.settings.openapiDocs.entryPrefix')}
                  </div>
                  <CodeSnippet value={selectedRow.path} copyable />
                </div>
                <div>
                  <div className="mb-1 text-xs font-medium text-[var(--color-text-2)]">
                    {t('system.settings.openapiDocs.docUrl')}
                  </div>
                  {selectedRow.docUrl ? (
                    <CodeSnippet value={selectedRow.docUrl} copyable />
                  ) : (
                    <CompactEmptyState
                      description={t('system.settings.openapiDocs.noDocUrl')}
                    />
                  )}
                </div>
              </div>
            ) : (
              <Tabs
                activeKey={activeTab}
                onChange={onTabChange}
                items={[
                  {
                    key: 'params',
                    label: (
                      <span className="flex items-center gap-1 text-xs">
                        <ApiOutlined />
                        <span>{t('system.settings.openapiDocs.tabParams')}</span>
                        {schemaRows.length > 0 && (
                          <span className="ml-1 rounded-full bg-[var(--color-fill-2)] px-1.5 py-0.2 text-[10px] text-[var(--color-text-3)]">
                            {schemaRows.length}
                          </span>
                        )}
                      </span>
                    ),
                    children: (
                      <div className="pt-2">
                        {schemaRows.length === 0 ? (
                          <div className="rounded border border-dashed border-[var(--color-border-1)] p-6 text-center text-xs text-[var(--color-text-3)]">
                            {t('system.settings.openapiDocs.noParams')}
                          </div>
                        ) : (
                          <CustomTable
                            rowKey="name"
                            size="small"
                            pagination={false}
                            autoScrollX={false}
                            columns={schemaColumns}
                            dataSource={schemaRows}
                            className="rounded border border-[var(--color-border-1)]"
                          />
                        )}
                      </div>
                    ),
                  },
                  {
                    key: 'example',
                    label: (
                      <span className="flex items-center gap-1 text-xs">
                        <CopyOutlined />
                        <span>{t('system.settings.openapiDocs.tabExample')}</span>
                      </span>
                    ),
                    children: (
                      <div className="space-y-4 pt-2">
                        <div>
                          <div className="mb-1 text-xs font-medium text-[var(--color-text-2)]">cURL</div>
                          <CodeSnippet
                            value={curlCommand}
                            copyable
                          />
                        </div>

                        {samplePayload ? (
                          <div>
                            <div className="mb-1 text-xs font-medium text-[var(--color-text-2)]">
                              {t('system.settings.openapiDocs.samplePayload')}
                            </div>
                            <CodeSnippet
                              value={JSON.stringify(samplePayload, null, 2)}
                              copyable
                            />
                          </div>
                        ) : null}
                      </div>
                    ),
                  },
                  {
                    key: 'security',
                    label: (
                      <span className="flex items-center gap-1 text-xs">
                        <SafetyCertificateOutlined />
                        <span>{t('system.settings.openapiDocs.tabSecurity')}</span>
                      </span>
                    ),
                    children: (
                      <div className="space-y-4 pt-2">
                        <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)]/40 p-3.5">
                          <div className="mb-1 text-xs font-semibold text-[var(--color-text-1)]">
                            {t('system.settings.openapiDocs.permissionControl')}
                          </div>
                          <div className="mb-2 text-xs text-[var(--color-text-3)]">
                            {t('system.settings.openapiDocs.permissionDesc')}
                          </div>
                          {selectedRow.permission ? (
                            <Tag className="m-0 border-[var(--color-border-1)] bg-[var(--color-fill-2)] font-mono text-xs font-semibold text-[var(--color-text-1)]">
                              {selectedRow.permission}
                            </Tag>
                          ) : (
                            <span className="text-xs text-[var(--color-text-3)]">
                              {t('system.settings.openapiDocs.unrestricted')}
                            </span>
                          )}
                        </div>

                        <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)]/40 p-3.5">
                          <div className="mb-1 text-xs font-semibold text-[var(--color-text-1)]">
                            {t('system.settings.openapiDocs.orgScope')}
                          </div>
                          <div className="text-xs leading-relaxed text-[var(--color-text-3)]">
                            {selectedRow.inject
                              ? t(injectDescriptionKey(selectedRow.inject))
                              : '--'}
                          </div>
                        </div>

                        <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)]/40 p-3.5">
                          <div className="mb-1 text-xs font-semibold text-[var(--color-text-1)]">
                            {t('system.settings.openapiDocs.authHeader')}
                          </div>
                          <div className="text-xs leading-relaxed text-[var(--color-text-2)]">
                            {t('system.settings.openapiDocs.authHeaderDesc')}{' '}
                            {authKeyHintBefore}
                            <Link
                              href={OPENAPI_SECRET_KEY_HREF}
                              className="text-[var(--color-primary)] hover:underline"
                            >
                              {t('system.settings.openapiDocs.authHeaderKeyPath')}
                            </Link>
                            {authKeyHintAfter}
                          </div>
                        </div>
                      </div>
                    ),
                  },
                ]}
              />
            )}
          </div>
        </div>
      )}
    </aside>
  );
};

export default OpenApiDocsDetail;
