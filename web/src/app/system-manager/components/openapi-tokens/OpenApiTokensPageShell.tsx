'use client';

import React, { useCallback, useMemo, useState } from 'react';
import { Button, Popconfirm, Table, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import TopSection from '@/components/top-section';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { formatScopeLabel } from '@/app/system-manager/utils/openapiTokens';
import OpenApiTokenCreateModal from './OpenApiTokenCreateModal';
import OpenApiTokenRevealModal from './OpenApiTokenRevealModal';
import type {
  OpenApiTokenCreateFormValues,
  OpenApiTokenExpiryStatus,
  OpenApiTokenScope,
  OpenApiTokenServiceCatalog,
  OpenApiTokenTab,
  PersonalOpenApiTokenRow,
  SystemOpenApiTokenRow,
} from './types';

type EditingTarget =
  | { kind: 'personal'; row: PersonalOpenApiTokenRow }
  | { kind: 'system'; row: SystemOpenApiTokenRow };

interface OpenApiTokensPageShellProps {
  canViewSystem?: boolean;
  canManagePersonal?: boolean;
  canManageSystem?: boolean;
  personalRows?: PersonalOpenApiTokenRow[];
  systemRows?: SystemOpenApiTokenRow[];
  scopeCatalog?: OpenApiTokenServiceCatalog[];
  personalLoading?: boolean;
  systemLoading?: boolean;
  onCreate?: (
    kind: OpenApiTokenTab,
    values: OpenApiTokenCreateFormValues,
  ) => string | void | Promise<string | void>;
  onEdit?: (
    kind: OpenApiTokenTab,
    id: number,
    values: OpenApiTokenCreateFormValues,
  ) => void | Promise<void>;
  onRevokePersonal?: (id: number) => void | Promise<void>;
  onRevokeSystem?: (id: number) => void | Promise<void>;
}

const toFormValues = (
  row: PersonalOpenApiTokenRow | SystemOpenApiTokenRow,
): OpenApiTokenCreateFormValues => ({
  name: row.name,
  systemId: 'systemId' in row ? row.systemId : undefined,
  expiresAt: row.expiresAt || undefined,
  scopeMode: row.scope?.mode === 'allowlist' ? 'allowlist' : 'all',
  scopeEndpoints: row.scope?.endpoints || [],
});

const OpenApiTokensPageShell: React.FC<OpenApiTokensPageShellProps> = ({
  canViewSystem = false,
  canManagePersonal = true,
  canManageSystem = true,
  personalRows = [],
  systemRows = [],
  personalLoading = false,
  systemLoading = false,
  scopeCatalog = [],
  onCreate,
  onEdit,
  onRevokePersonal,
  onRevokeSystem,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tab, setTab] = useState<OpenApiTokenTab>('personal');
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<EditingTarget | null>(null);
  const [revealSecret, setRevealSecret] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const canManageCurrent = tab === 'system' ? canManageSystem : canManagePersonal;
  const formKind = editing?.kind ?? tab;
  const formOpen = createOpen || Boolean(editing);
  const allLabel = t('system.settings.secret.scopeAll');

  const expiryTag = (status: OpenApiTokenExpiryStatus) => {
    if (status === 'expired') {
      return (
        <Tag bordered={false} color="error" className="m-0 text-xs">
          {t('system.settings.secret.expired')}
        </Tag>
      );
    }
    if (status === 'never') {
      return (
        <Tag bordered={false} color="blue" className="m-0 text-xs">
          {t('system.settings.secret.neverExpires')}
        </Tag>
      );
    }
    return (
      <Tag bordered={false} color="success" className="m-0 text-xs">
        {t('system.settings.secret.active')}
      </Tag>
    );
  };

  const renderActions = (
    onEditClick: () => void,
    onDelete: () => void,
    canManage: boolean,
  ) => (
    canManage ? (
      <div className="flex items-center gap-3">
        <Button type="link" className="px-0" onClick={onEditClick}>
          {t('common.edit')}
        </Button>
        <Popconfirm
          title={t('system.settings.secret.deleteConfirm')}
          onConfirm={onDelete}
          okText={t('common.yes')}
          cancelText={t('common.no')}
        >
          <Button type="link" danger className="px-0">
            {t('common.delete')}
          </Button>
        </Popconfirm>
      </div>
    ) : null
  );

  const renderScope = (scope: OpenApiTokenScope | null) => (
    <EllipsisWithTooltip
      className="block max-w-md truncate text-[var(--color-text-2)] xl:max-w-xl"
      text={formatScopeLabel(scope, allLabel)}
    />
  );

  const personalColumns: ColumnsType<PersonalOpenApiTokenRow> = [
    {
      title: t('system.settings.secret.name'),
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string) => (
        <span className="font-medium text-[var(--color-text-1)]">
          {value || '—'}
        </span>
      ),
    },
    {
      title: t('system.settings.secret.key'),
      dataIndex: 'preview',
      width: 170,
      render: (value: string) => (
        <span className="select-all rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-2 py-0.5 font-mono text-xs tracking-wider text-[var(--color-text-2)]">
          {value}
        </span>
      ),
    },
    {
      title: t('system.settings.secret.group'),
      dataIndex: 'teamName',
      width: 130,
      render: (value: string) => (
        <span className="text-[var(--color-text-2)]">{value || '—'}</span>
      ),
    },
    {
      title: t('system.settings.secret.scope'),
      dataIndex: 'scope',
      render: renderScope,
    },
    {
      title: t('system.settings.secret.status'),
      dataIndex: 'status',
      width: 110,
      render: (status: OpenApiTokenExpiryStatus) => expiryTag(status),
    },
    {
      title: t('system.settings.secret.createdAt'),
      dataIndex: 'createdAt',
      width: 170,
      render: (value: string) => (
        <span className="text-xs text-[var(--color-text-3)]">
          {convertToLocalizedTime(value)}
        </span>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 120,
      render: (_, record) => renderActions(
        () => setEditing({ kind: 'personal', row: record }),
        () => onRevokePersonal?.(record.id),
        canManagePersonal,
      ),
    },
  ];

  const systemColumns: ColumnsType<SystemOpenApiTokenRow> = [
    {
      title: t('system.settings.secret.systemId'),
      dataIndex: 'systemId',
      width: 140,
      render: (value: string) => (
        <span className="inline-block rounded border border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-2 py-0.5 font-mono text-xs font-medium text-[var(--color-text-2)]">
          {value}
        </span>
      ),
    },
    {
      title: t('system.settings.secret.name'),
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string) => (
        <span className="font-medium text-[var(--color-text-1)]">
          {value || '—'}
        </span>
      ),
    },
    {
      title: t('system.settings.secret.key'),
      dataIndex: 'preview',
      width: 170,
      render: (value: string) => (
        <span className="select-all rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-2 py-0.5 font-mono text-xs tracking-wider text-[var(--color-text-2)]">
          {value}
        </span>
      ),
    },
    {
      title: t('system.settings.secret.scope'),
      dataIndex: 'scope',
      render: renderScope,
    },
    {
      title: t('system.settings.secret.status'),
      width: 110,
      render: (_, record) => expiryTag(record.status),
    },
    {
      title: t('system.settings.secret.createdAt'),
      dataIndex: 'createdAt',
      width: 170,
      render: (value: string) => (
        <span className="text-xs text-[var(--color-text-3)]">
          {convertToLocalizedTime(value)}
        </span>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 120,
      render: (_, record) => renderActions(
        () => setEditing({ kind: 'system', row: record }),
        () => onRevokeSystem?.(record.id),
        canManageSystem,
      ),
    },
  ];

  const tabItems = useMemo(() => {
    const personal = {
      key: 'personal',
      label: t('system.settings.secret.personalTab'),
    };
    if (!canViewSystem) {
      return [personal];
    }
    return [
      personal,
      {
        key: 'system',
        label: t('system.settings.secret.systemTab'),
      },
    ];
  }, [canViewSystem, t]);

  const closeForm = useCallback(() => {
    setCreateOpen(false);
    setEditing(null);
  }, []);

  const editingValues = useMemo(
    () => (editing ? toFormValues(editing.row) : undefined),
    [editing],
  );

  const handleSubmit = useCallback(async (values: OpenApiTokenCreateFormValues) => {
    setSubmitting(true);
    try {
      if (editing) {
        await onEdit?.(editing.kind, editing.row.id, values);
        closeForm();
        return;
      }
      const secret = await onCreate?.(tab, values);
      closeForm();
      if (typeof secret === 'string' && secret) {
        setRevealSecret(secret);
      }
    } finally {
      setSubmitting(false);
    }
  }, [closeForm, editing, onCreate, onEdit, tab]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-4 shrink-0">
        <TopSection
          title={t('system.settings.secret.title')}
          content={t('system.settings.secret.content')}
        />
      </div>
      <section className="flex min-h-0 flex-1 flex-col rounded-md bg-[var(--color-bg)] p-4">
        <Tabs
          activeKey={tab}
          onChange={(key) => setTab(key as OpenApiTokenTab)}
          items={tabItems}
          className="[&>.ant-tabs-nav]:mb-4 [&>.ant-tabs-content-holder]:hidden"
          tabBarExtraContent={
            canManageCurrent ? (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setEditing(null);
                  setCreateOpen(true);
                }}
              >
                {t('common.new')}
              </Button>
            ) : null
          }
        />
        <div className="min-h-0 flex-1 overflow-auto">
          {tab === 'system' ? (
            <Table<SystemOpenApiTokenRow>
              rowKey="id"
              size="middle"
              loading={systemLoading}
              pagination={false}
              columns={systemColumns}
              dataSource={systemRows}
              locale={{
                emptyText: (
                  <CompactEmptyState
                    className="py-12"
                    description={t('system.settings.secret.emptySystem')}
                  />
                ),
              }}
            />
          ) : (
            <Table<PersonalOpenApiTokenRow>
              rowKey="id"
              size="middle"
              loading={personalLoading}
              pagination={false}
              columns={personalColumns}
              dataSource={personalRows}
              locale={{
                emptyText: (
                  <CompactEmptyState
                    className="py-12"
                    description={t('system.settings.secret.emptyPersonal')}
                  />
                ),
              }}
            />
          )}
        </div>
      </section>

      <OpenApiTokenCreateModal
        open={formOpen}
        kind={formKind}
        catalog={scopeCatalog}
        editing={Boolean(editing)}
        initialValues={editingValues}
        submitting={submitting}
        onCancel={closeForm}
        onSubmit={handleSubmit}
      />
      <OpenApiTokenRevealModal
        open={Boolean(revealSecret)}
        secret={revealSecret}
        onClose={() => setRevealSecret('')}
      />
    </div>
  );
};

export default OpenApiTokensPageShell;
