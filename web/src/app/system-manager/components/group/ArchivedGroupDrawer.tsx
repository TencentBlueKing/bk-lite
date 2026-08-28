'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Modal, Tag, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { isSilentRequestError } from '@/utils/request';
import { useGroupApi } from '@/app/system-manager/api/group';
import { getArchivedActionPresentation } from '@/app/system-manager/utils/archivedGroupActions';
import PermissionWrapper from '@/components/permission';
import CustomTable from '@/components/custom-table';
import styles from './ArchivedGroupDrawer.module.scss';
import type {
  ArchivedGroupChildNode,
  ArchivedGroupKind,
  ArchivedGroupRoot,
} from '@/app/system-manager/types/archived-group';

export interface ArchivedGroupDrawerProps {
  open: boolean;
  onClose: () => void;
  /** 恢复 / 永久删除成功后回调（由页面刷新正常树与登录组织上下文） */
  onChanged: () => Promise<void> | void;
}

const KIND_TAG_COLOR: Record<ArchivedGroupKind, string> = {
  local: 'blue',
  synced_active_source: 'orange',
  synced_deleted_source: 'orange',
};

/** 树表行：叶子不带 children，避免 Ant Design 画出空的展开图标 */
type ArchivedTableRow = {
  id: number;
  name: string;
  parent_id: number;
  kind?: ArchivedGroupKind;
  can_restore?: boolean;
  can_permanently_delete?: boolean;
  children?: ArchivedTableRow[];
};

function toArchivedTableRows(
  nodes: Array<ArchivedGroupRoot | ArchivedGroupChildNode>,
  inheritedKind?: ArchivedGroupKind,
): ArchivedTableRow[] {
  return nodes.map((node) => {
    const kind = 'kind' in node ? node.kind : inheritedKind;
    const row: ArchivedTableRow = {
      id: node.id,
      name: node.name,
      parent_id: node.parent_id,
      kind,
    };
    if ('kind' in node) {
      row.can_restore = node.can_restore;
      row.can_permanently_delete = node.can_permanently_delete;
    }
    if (node.children?.length) {
      row.children = toArchivedTableRows(node.children, kind);
    }
    return row;
  });
}

function countDescendants(nodes: ArchivedTableRow[] = []): number {
  return nodes.reduce((sum, node) => sum + 1 + countDescendants(node.children), 0);
}

const ArchivedGroupDrawer: React.FC<ArchivedGroupDrawerProps> = ({
  open,
  onClose,
  onChanged,
}) => {
  const { t } = useTranslation();
  const { listArchivedGroups, restoreArchivedGroup, permanentlyDeleteArchivedGroup } = useGroupApi();
  const { confirm } = Modal;

  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [roots, setRoots] = useState<ArchivedGroupRoot[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const tableData = useMemo(() => toArchivedTableRows(roots), [roots]);
  const childrenTruncated = useMemo(
    () => roots.some((root) => root.children_truncated === true),
    [roots],
  );

  const applyPage = useCallback((listed: { items: ArchivedGroupRoot[]; count: number; page: number; page_size: number }) => {
    setRoots(listed.items);
    setTotal(listed.count);
    setPage(listed.page);
    setPageSize(listed.page_size);
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const listed = await listArchivedGroups({ page: 1, pageSize });
        if (!cancelled) {
          applyPage(listed);
        }
      } catch {
        if (!cancelled) {
          message.error(t('common.fetchFailed'));
          applyPage({ items: [], count: 0, page: 1, page_size: pageSize });
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
    // listArchivedGroups 每次 render 新引用，仅随 open 触发加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, t]);

  const reloadArchived = useCallback(async (nextPage = page, nextPageSize = pageSize) => {
    setLoading(true);
    try {
      const listed = await listArchivedGroups({ page: nextPage, pageSize: nextPageSize });
      if (listed.items.length === 0 && listed.page > 1 && listed.count > 0) {
        const fallback = await listArchivedGroups({ page: listed.page - 1, pageSize: nextPageSize });
        applyPage(fallback);
        return;
      }
      applyPage(listed);
    } catch {
      message.error(t('common.fetchFailed'));
      applyPage({ items: [], count: 0, page: nextPage, page_size: nextPageSize });
    } finally {
      setLoading(false);
    }
    // listArchivedGroups 每次 render 新引用
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyPage, page, pageSize, t]);

  const kindLabel = useCallback((kind: ArchivedGroupKind) => {
    if (kind === 'local') {
      return t('system.group.archivedKind.local');
    }
    return t('system.group.archivedKind.synced');
  }, [t]);

  const handleRestore = useCallback((root: ArchivedTableRow) => {
    confirm({
      title: t('system.group.restoreConfirm'),
      content: t('system.group.restoreConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        setActionLoadingId(root.id);
        try {
          await restoreArchivedGroup({ id: root.id });
          message.success(t('system.group.restoreSuccess'));
          await onChanged();
          await reloadArchived();
        } catch (err) {
          if (isSilentRequestError(err)) {
            return;
          }
          const msg = err instanceof Error && err.message ? err.message : t('system.group.restoreFailed');
          message.error(msg);
        } finally {
          setActionLoadingId(null);
        }
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirm, onChanged, reloadArchived, t]);

  const handlePermanentlyDelete = useCallback((root: ArchivedTableRow) => {
    confirm({
      title: t('system.group.permanentlyDeleteConfirm'),
      content: root.kind && root.kind !== 'local'
        ? t('system.group.permanentlyDeleteConfirmCxtSynced')
        : t('system.group.permanentlyDeleteConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      async onOk() {
        setActionLoadingId(root.id);
        try {
          await permanentlyDeleteArchivedGroup({ id: root.id });
          message.success(t('system.group.permanentlyDeleteSuccess'));
          await onChanged();
          await reloadArchived();
        } catch (err) {
          if (isSilentRequestError(err)) {
            return;
          }
          const msg = err instanceof Error && err.message
            ? err.message
            : t('system.group.permanentlyDeleteFailed');
          message.error(msg);
        } finally {
          setActionLoadingId(null);
        }
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirm, onChanged, reloadArchived, t]);

  const columns: ColumnsType<ArchivedTableRow> = useMemo(() => [
    {
      title: t('system.group.archivedColumns.name'),
      dataIndex: 'name',
      key: 'name',
      width: 240,
    },
    {
      title: t('system.group.archivedColumns.kind'),
      dataIndex: 'kind',
      key: 'kind',
      width: 150,
      render: (kind: ArchivedGroupKind | undefined) => (
        kind ? (
          <Tag color={KIND_TAG_COLOR[kind]} className="m-0">
            {kindLabel(kind)}
          </Tag>
        ) : '--'
      ),
    },
    {
      title: t('system.group.archivedColumns.subtreeCount'),
      key: 'subtreeCount',
      width: 100,
      render: (_: unknown, root: ArchivedTableRow) => countDescendants(root.children) || '--',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 180,
      render: (_: unknown, root: ArchivedTableRow) => {
        const presentation = getArchivedActionPresentation(root);
        if (presentation.type === 'empty') {
          return null;
        }
        if (presentation.type === 'sync_reconcile_reason') {
          return (
            <Tooltip title={t('system.group.syncReconcileArchivedHint')}>
              <span className="cursor-help text-[var(--color-text-3)]">
                {t('system.group.syncReconcileArchived')}
              </span>
            </Tooltip>
          );
        }
        return (
          <>
            {presentation.can_restore ? (
              <PermissionWrapper requiredPermissions={['Delete Group']}>
                <Button
                  type="link"
                  className="mr-[8px] p-0"
                  loading={actionLoadingId === root.id}
                  onClick={() => handleRestore(root)}
                >
                  {t('system.group.restore')}
                </Button>
              </PermissionWrapper>
            ) : null}
            {presentation.can_permanently_delete ? (
              <PermissionWrapper requiredPermissions={['Delete Group']}>
                <Button
                  type="link"
                  className="p-0"
                  danger
                  loading={actionLoadingId === root.id}
                  onClick={() => handlePermanentlyDelete(root)}
                >
                  {t('system.group.permanentlyDelete')}
                </Button>
              </PermissionWrapper>
            ) : null}
          </>
        );
      },
    },
  ], [actionLoadingId, handlePermanentlyDelete, handleRestore, kindLabel, t]);

  return (
    <Drawer
      title={t('system.group.archivedDrawerTitle')}
      open={open}
      onClose={onClose}
      width={720}
      destroyOnClose
    >
      <div className={styles.tableWrap}>
        {childrenTruncated ? (
          <Alert
            type="warning"
            showIcon
            className="mb-[12px]"
            message={t('system.group.childrenTruncated')}
          />
        ) : null}
        <CustomTable
          rowKey="id"
          tableLayout="fixed"
          scroll={{ y: 'calc(100vh - 205px)' }}
          loading={loading}
          dataSource={tableData}
          columns={columns}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100],
            onChange: (nextPage, nextPageSize) => {
              void reloadArchived(nextPage, nextPageSize);
            },
          }}
          autoScrollX={false}
          expandable={{
            indentSize: 20,
            rowExpandable: (record) => Boolean(record.children?.length),
          }}
          locale={{ emptyText: t('system.group.archivedEmpty') }}
        />
      </div>
    </Drawer>
  );
};

export default ArchivedGroupDrawer;
