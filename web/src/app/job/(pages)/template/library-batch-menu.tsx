import React, { useState } from 'react';
import { Button, Dropdown, message } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import usePermissions from '@/hooks/usePermissions';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import AdjustOrganizationsModal from '@/app/job/components/adjust-organizations-modal';

type LibraryActions =
  | { resource: 'script'; onImport: () => void; onExport: (ids: number[]) => void }
  | { resource: 'playbook' };

interface BatchAction {
  kind: 'adjust' | 'confirmDelete' | 'deleting';
  ids: number[];
}

type Props = LibraryActions & {
  selectedIds: number[];
  busy: boolean;
  selectionVersion: React.RefObject<number>;
  deleteItems: (ids: number[]) => Promise<{ deleted_count: number }>;
  onSuccess: () => void;
};

export default function LibraryBatchMenu(props: Props) {
  const { t } = useTranslation();
  const { hasPermission } = usePermissions();
  const [action, setAction] = useState<BatchAction | null>(null);
  const { selectedIds, resource } = props;
  const canChange = !props.busy && selectedIds.length > 0;
  const canEdit = hasPermission(['Edit']);
  const canDelete = hasPermission(['Delete']);
  const canExport = resource === 'script' && hasPermission(['View']);
  const canImport = resource === 'script' && hasPermission(['Add']);
  const disabled = !canImport && !(canChange && (canEdit || canDelete || canExport));

  const finish = () => {
    setAction(null);
    props.onSuccess();
  };
  const confirmDelete = async () => {
    if (!canDelete || action?.kind !== 'confirmDelete') return;
    const version = props.selectionVersion.current;
    setAction({ ...action, kind: 'deleting' });
    try {
      const { deleted_count } = await props.deleteItems(action.ids);
      if (version !== props.selectionVersion.current) return;
      message.success(t(resource === 'script' ? 'job.batchDeleteScriptsSuccess' : 'job.batchDeletePlaybooksSuccess', '', { count: deleted_count }));
      finish();
    } catch {
      if (version === props.selectionVersion.current) setAction(action);
    }
  };

  return (
    <>
      <Dropdown
        disabled={disabled}
        trigger={['click']}
        menu={{ items: [
          {
            key: 'adjust',
            label: t('job.targetOrganizations.title'),
            disabled: !canChange || !canEdit,
            onClick: () => setAction({ kind: 'adjust', ids: selectedIds }),
          },
          ...(props.resource === 'script' ? [
            { key: 'import', label: t('job.batchImportScripts'), disabled: !canImport, onClick: props.onImport },
            { key: 'export', label: t('job.batchExportScripts'), disabled: !canChange || !canExport, onClick: () => props.onExport(selectedIds) },
          ] : []),
          {
            key: 'delete',
            label: t('common.batchDelete'),
            disabled: !canChange || !canDelete,
            danger: true,
            onClick: () => setAction({ kind: 'confirmDelete', ids: selectedIds }),
          },
        ] }}
      >
        <Button disabled={disabled} aria-label={t('common.batchOperation')}>
          {t('common.batchOperation')} <DownOutlined />
        </Button>
      </Dropdown>
      {canEdit && action?.kind === 'adjust' && (
        <AdjustOrganizationsModal resource={resource} ids={action.ids} onCancel={() => setAction(null)} onSuccess={finish} />
      )}
      {canDelete && action && action.kind !== 'adjust' && (
        <OperateModal
          open
          title={t('common.batchDelete')}
          onOk={confirmDelete}
          okText={t('common.delete')}
          okButtonProps={{ danger: true }}
          confirmLoading={action.kind === 'deleting'}
          onCancel={() => setAction(null)}
          cancelText={t('common.cancel')}
          cancelButtonProps={{ disabled: action.kind === 'deleting' }}
          closable={action.kind !== 'deleting'}
          keyboard={action.kind !== 'deleting'}
        >
          {t(resource === 'script' ? 'job.batchDeleteScriptsConfirm' : 'job.batchDeletePlaybooksConfirm', '', { count: action.ids.length })}
        </OperateModal>
      )}
    </>
  );
}
