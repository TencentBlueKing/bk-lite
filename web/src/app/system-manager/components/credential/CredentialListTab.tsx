'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Input, message, Popconfirm, Space, Switch, Tag, Tooltip, Typography } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import {
  AppstoreOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  HddOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import { CREDENTIAL_CATEGORIES } from '@/components/credential-picker/types';
import type { CredentialGroupOption, CredentialItem, CredentialTypeItem } from '@/components/credential-picker/types';
import { useCredentialApi } from '@/app/system-manager/api/credential';
import CredentialFormDrawer, { type CredentialDrawerMode } from './CredentialFormDrawer';
import type { ColumnItem } from '@/types';
import { HandledRequestError } from '@/utils/request';

interface CredentialListTabProps {
  onGoTypes: () => void;
  active?: boolean;
}

const ALL_TYPES = '__all__';

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  host: <DesktopOutlined />,
  network: <ShareAltOutlined />,
  storage: <HddOutlined />,
  database: <DatabaseOutlined />,
  middleware: <ClusterOutlined />,
  cloud: <CloudServerOutlined />,
  other: <AppstoreOutlined />,
};

const CredentialListTab: React.FC<CredentialListTabProps> = ({ onGoTypes, active = true }) => {
  const { t } = useTranslation();
  const {
    getCredentialTypes,
    getCredentials,
    getCredential,
    createCredential,
    updateCredential,
    deleteCredential,
    setCredentialDisabled,
    getAssignableGroups,
    getUsableGroups,
  } = useCredentialApi();
  const [types, setTypes] = useState<CredentialTypeItem[]>([]);
  const [items, setItems] = useState<CredentialItem[]>([]);
  const [assignableGroups, setAssignableGroups] = useState<CredentialGroupOption[]>([]);
  const [usableGroups, setUsableGroups] = useState<CredentialGroupOption[]>([]);
  const [category, setCategory] = useState<string>(CREDENTIAL_CATEGORIES[0]);
  const [typeKey, setTypeKey] = useState<string>(ALL_TYPES);
  const [search, setSearch] = useState('');
  const [ownerId, setOwnerId] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<CredentialDrawerMode>('create');
  const [current, setCurrent] = useState<CredentialItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequestSeq = useRef(0);

  const categoryLabel = (id: string) => t(`system.credential.categories.${id}`, id);
  const groupName = (id: number) => usableGroups.find((item) => item.id === id)?.name
    || assignableGroups.find((item) => item.id === id)?.name
    || String(id);
  const canManageOwner = (groupId: number) => assignableGroups.some((item) => item.id === groupId);

  const navCategories = useMemo(() => {
    const extra = types.flatMap((item) => item.categories).filter((id) => !CREDENTIAL_CATEGORIES.includes(id as typeof CREDENTIAL_CATEGORIES[number]));
    return [...CREDENTIAL_CATEGORIES, ...Array.from(new Set(extra))];
  }, [types]);

  const categoryTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const cat of navCategories) {
      counts[cat] = types.filter((item) => item.categories.includes(cat)).length;
    }
    return counts;
  }, [navCategories, types]);

  const typesInCategory = useMemo(
    () => types.filter((item) => item.categories.includes(category)),
    [types, category],
  );

  const loadMeta = async () => {
    const [nextTypes, nextAssignable, nextUsable] = await Promise.all([
      getCredentialTypes({ page_size: 0 }),
      getAssignableGroups(),
      getUsableGroups(),
    ]);
    setTypes(nextTypes.items);
    setAssignableGroups(nextAssignable);
    setUsableGroups(nextUsable);
  };

  const loadList = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    nextType = typeKey,
    nextOwner = ownerId,
    keyword = search,
  ) => {
    setLoading(true);
    try {
      const data = await getCredentials({
        search: keyword,
        category,
        type: nextType === ALL_TYPES ? undefined : nextType,
        group_id: nextOwner,
        page,
        page_size: pageSize,
      });
      setItems(data.items);
      setPagination({ current: page, pageSize, total: data.count });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const credentialActionError = (error: unknown) => {
    const code = error instanceof HandledRequestError ? error.message : '';
    if (code === 'in_use') {
      return t('system.credential.inUse');
    }
    return t('common.delFailed');
  };

  const confirmDelete = async (credentialId: string) => {
    try {
      await deleteCredential(credentialId);
      await loadList();
    } catch (error) {
      message.error(credentialActionError(error));
    }
  };

  const reload = async () => {
    await loadMeta();
    await loadList();
  };

  useEffect(() => {
    if (!active) {
      return;
    }
    void loadMeta();
  }, [active]);

  useEffect(() => {
    setTypeKey(ALL_TYPES);
    void loadList(1, pagination.pageSize, ALL_TYPES, ownerId, search);
  }, [category]);

  const openCreate = () => {
    if (!typesInCategory.length) {
      message.info(t('system.credential.noTypeHint'));
      return;
    }
    detailRequestSeq.current += 1;
    setDetailLoading(false);
    setCurrent(null);
    setDrawerMode('create');
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    detailRequestSeq.current += 1;
    setDetailLoading(false);
    setDrawerOpen(false);
  };

  const openRecord = (record: CredentialItem, mode: CredentialDrawerMode) => {
    const requestId = ++detailRequestSeq.current;
    setCurrent(record);
    setDrawerMode(mode);
    setDrawerOpen(true);
    setDetailLoading(true);
    void getCredential(record.credential_id)
      .then((detail) => {
        if (requestId !== detailRequestSeq.current) {
          return;
        }
        setCurrent(detail);
      })
      .catch(() => {
        if (requestId !== detailRequestSeq.current) {
          return;
        }
        message.error(t('common.fetchFailed'));
      })
      .finally(() => {
        if (requestId === detailRequestSeq.current) {
          setDetailLoading(false);
        }
      });
  };

  const lockedType = typeKey === ALL_TYPES ? undefined : typeKey;

  const columns: ColumnItem[] = [
    {
      title: t('system.credential.name'),
      dataIndex: 'name',
      key: 'name',
      width: 320,
      render: (_, record: CredentialItem) => (
        <div className="flex items-center gap-2.5 py-0.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]">
            <KeyOutlined className="text-sm" />
          </div>
          <div className="min-w-0 flex-1">
            <div>
              <Button
                type="link"
                className="!h-auto !p-0 font-medium text-[var(--color-text-1)] hover:!text-[var(--color-primary)]"
                onClick={() => openRecord(record, 'view')}
              >
                {record.name}
              </Button>
            </div>
            <div className="mt-0.5">
              <Typography.Text className="font-mono text-xs text-[var(--color-text-3)]" copyable>
                {record.credential_id}
              </Typography.Text>
            </div>
          </div>
        </div>
      ),
    },
    {
      title: t('system.credential.type'),
      dataIndex: 'type',
      key: 'type',
      width: 140,
      render: (key: string) => (
        <Tag bordered={false} className="rounded bg-[var(--color-fill-2)] px-2 py-0.5 font-medium text-[var(--color-text-2)]">
          {types.find((item) => item.key === key)?.name || key}
        </Tag>
      ),
    },
    {
      title: t('system.credential.organization'),
      dataIndex: 'group_id',
      key: 'group_id',
      width: 140,
      render: (id: number) => <span className="text-sm text-[var(--color-text-2)]">{groupName(id)}</span>,
    },
    {
      title: t('system.credential.refs'),
      dataIndex: 'refs',
      key: 'refs',
      width: 110,
      render: (refs: unknown) => {
        if (refs == null || (Array.isArray(refs) && refs.length === 0) || refs === '') {
          return <span className="text-[var(--color-text-4)]">—</span>;
        }
        if (Array.isArray(refs)) {
          const labelOf = (moduleName: string, count: number) => {
            if (moduleName === 'cmdb') {
              return t('system.credential.refCmdb', 'CMDB {count}', { count });
            }
            if (moduleName === 'monitor') {
              return t('system.credential.refMonitor', '监控 {count}', { count });
            }
            return `${moduleName} ${count}`;
          };
          return (
            <div className="flex flex-wrap gap-1">
              {refs.map((item) => {
                const moduleName =
                  item && typeof item === 'object'
                    ? String((item as { module?: string }).module || '')
                    : '';
                const count = item && typeof item === 'object' ? Number((item as { count?: number }).count) : 0;
                if (!moduleName || !count) {
                  return null;
                }
                return (
                  <Tag key={moduleName} bordered={false} color="blue" className="rounded">
                    {labelOf(moduleName, count)}
                  </Tag>
                );
              })}
            </div>
          );
        }
        return <span className="text-sm text-[var(--color-text-2)]">{String(refs)}</span>;
      },
    },
    {
      title: t('system.credential.enabled'),
      dataIndex: 'disabled',
      key: 'disabled',
      width: 90,
      align: 'center',
      render: (disabled: boolean, record: CredentialItem) => (
        canManageOwner(record.group_id) ? (
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Switch
              size="small"
              checked={!disabled}
              onChange={(checked) => void setCredentialDisabled(record.credential_id, !checked).then(() => loadList())}
            />
          </PermissionWrapper>
        ) : (
          <span className="text-sm text-[var(--color-text-3)]">
            {disabled ? t('common.disable') : t('system.credential.enabled')}
          </span>
        )
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      dataIndex: 'actions',
      width: 180,
      render: (_, record: CredentialItem) => (
        <Space size={4}>
          {canManageOwner(record.group_id) ? (
            <>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  type="link"
                  size="small"
                  className="!px-1.5"
                  onClick={() => openRecord(record, 'edit')}
                >
                  {t('common.edit')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper requiredPermissions={['Delete']}>
                <Popconfirm title={t('common.delConfirm')} onConfirm={() => confirmDelete(record.credential_id)}>
                  <Button
                    type="link"
                    size="small"
                    danger
                    className="!px-1.5"
                  >
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </PermissionWrapper>
            </>
          ) : (
            <Button
              type="link"
              size="small"
              className="!px-1.5"
              onClick={() => openRecord(record, 'view')}
            >
              {t('common.detail')}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* Left side: Category Navigation Bar (Primary Level) */}
      <div className="flex w-[190px] shrink-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)]">
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-[var(--color-border-2)] bg-[var(--color-fill-1)]/60 px-3.5">
          <span className="text-xs font-semibold text-[var(--color-text-2)]">
            {t('system.credential.category')}
          </span>
          <span className="rounded-full bg-[var(--color-fill-2)] px-2 py-0.5 text-[11px] text-[var(--color-text-3)]">
            {navCategories.length}
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {navCategories.map((id) => {
            const active = category === id;
            const count = categoryTypeCounts[id] ?? 0;
            return (
              <button
                key={id}
                type="button"
                className={`group relative mb-1.5 flex w-full items-center justify-between rounded-md py-2.5 pl-3 pr-2.5 text-left text-sm transition-all duration-150 ${
                  active
                    ? 'bg-[var(--color-primary-bg-active)] font-medium text-[var(--color-primary)]'
                    : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)]'
                }`}
                onClick={() => setCategory(id)}
              >
                {/* Active accent pill on the left */}
                {active && (
                  <span className="absolute inset-y-2 left-0 w-1 rounded-r-sm bg-[var(--color-primary)]" />
                )}
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={`text-base transition-colors ${
                      active
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-3)] group-hover:text-[var(--color-text-2)]'
                    }`}
                  >
                    {CATEGORY_ICONS[id] || <AppstoreOutlined />}
                  </span>
                  <span className="truncate">{categoryLabel(id)}</span>
                </div>
                {count > 0 ? (
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] leading-tight ${
                      active
                        ? 'bg-[var(--color-primary)]/15 font-semibold text-[var(--color-primary)]'
                        : 'bg-[var(--color-fill-2)] text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)]'
                    }`}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      {/* Right side: Type Pills (Secondary Level) + Filter/Actions + Table */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar: Type Filter Pills (Pills) on the left, Search & Actions on the right */}
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-2)] pb-3">
          {/* Secondary Level: Segmented Tab-style Filter */}
          <div className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-fill-1)] p-1">
            <button
              type="button"
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
                typeKey === ALL_TYPES
                  ? 'bg-[var(--color-bg)] text-[var(--color-primary)] shadow-xs'
                  : 'text-[var(--color-text-2)] hover:text-[var(--color-text-1)]'
              }`}
              onClick={() => {
                setTypeKey(ALL_TYPES);
                void loadList(1, pagination.pageSize, ALL_TYPES);
              }}
            >
              <span>{t('system.credential.allTypes')}</span>
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] leading-tight ${
                  typeKey === ALL_TYPES
                    ? 'bg-[var(--color-primary-bg-active)] font-semibold text-[var(--color-primary)]'
                    : 'bg-[var(--color-fill-2)] text-[var(--color-text-4)]'
                }`}
              >
                {typesInCategory.length}
              </span>
            </button>
            {typesInCategory.map((item) => {
              const active = typeKey === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  className={`inline-flex items-center rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
                    active
                      ? 'bg-[var(--color-bg)] text-[var(--color-primary)] shadow-xs'
                      : 'text-[var(--color-text-2)] hover:text-[var(--color-text-1)]'
                  }`}
                  onClick={() => {
                    setTypeKey(item.key);
                    void loadList(1, pagination.pageSize, item.key);
                  }}
                >
                  <span>{item.name}</span>
                </button>
              );
            })}
          </div>

          {/* Search, Filter & Operation Tools */}
          <div className="flex flex-wrap items-center gap-2">
            <Input.Search
              allowClear
              className="w-56"
              placeholder={t('common.search')}
              onSearch={(value) => {
                setSearch(value);
                void loadList(1, pagination.pageSize, typeKey, ownerId, value);
              }}
            />
            <div className="w-56">
              <GroupTreeSelect
                multiple={false}
                mode="ownership"
                allowClear
                showSearch
                placeholder={t('system.credential.organization')}
                value={ownerId}
                onChange={(value) => {
                  const next = typeof value === 'number' ? value : undefined;
                  setOwnerId(next);
                  void loadList(1, pagination.pageSize, typeKey, next);
                }}
              />
            </div>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                {t('system.credential.addCredential')}
              </Button>
            </PermissionWrapper>
            <Tooltip title={t('common.refresh')}>
              <Button type="text" icon={<ReloadOutlined />} onClick={() => void reload()} />
            </Tooltip>
          </div>
        </div>

        {/* Content Table / Empty */}
        <div className="min-h-0 flex-1">
          {!typesInCategory.length && !loading ? (
            <div className="flex h-full min-h-[300px] flex-col items-center justify-center rounded-lg border border-dashed border-[var(--color-border-2)] bg-[var(--color-fill-1)]/20 p-8 text-center">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={(
                  <div className="space-y-3">
                    <p className="text-sm text-[var(--color-text-3)]">
                      {t('system.credential.noTypeHint')}
                    </p>
                    <Button type="primary" ghost size="small" onClick={onGoTypes}>
                      {t('system.credential.goTypes')}
                    </Button>
                  </div>
                )}
              />
            </div>
          ) : (
            <CustomTable
              rowKey="credential_id"
              loading={loading}
              columns={columns}
              dataSource={items}
              pagination={{
                current: pagination.current,
                pageSize: pagination.pageSize,
                total: pagination.total,
                showSizeChanger: true,
                onChange: (page, pageSize) => void loadList(page, pageSize),
              }}
            />
          )}
        </div>
      </div>
      <CredentialFormDrawer
        open={drawerOpen}
        mode={drawerMode}
        types={typeKey === ALL_TYPES ? typesInCategory : typesInCategory.filter((item) => item.key === typeKey)}
        groups={assignableGroups}
        lockedType={lockedType}
        record={current}
        loading={detailLoading}
        onClose={closeDrawer}
        onSubmit={async (payload) => {
          if (drawerMode === 'create') {
            await createCredential(payload);
          } else if (current) {
            await updateCredential(current.credential_id, payload);
          }
          await loadList();
        }}
      />
    </div>
  );
};

export default CredentialListTab;
