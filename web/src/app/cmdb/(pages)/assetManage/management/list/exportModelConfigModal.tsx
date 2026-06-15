'use client';

import React, {
  useState,
  useMemo,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Button, Input, Tree, message } from 'antd';
import type { DataNode } from 'antd/es/tree';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useAuth } from '@/context/auth';
import { useSession } from 'next-auth/react';
import { GroupItem } from '@/app/cmdb/types/assetManage';

interface ExportModelConfigModalProps {
  modelGroup: GroupItem[];
}

export interface ExportModelConfigModalRef {
  showModal: () => void;
}

const ExportModelConfigModal = forwardRef<
  ExportModelConfigModalRef,
  ExportModelConfigModalProps
>(({ modelGroup }, ref) => {
  const { t } = useTranslation();
  const { exportModelConfig } = useModelApi();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = (session?.user as any)?.token || authContext?.token || null;
  const tokenRef = useRef(token);

  const [visible, setVisible] = useState<boolean>(false);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [checkedKeys, setCheckedKeys] = useState<string[]>([]);
  const [searchValue, setSearchValue] = useState<string>('');

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const allModelIds = useMemo(
    () => modelGroup.flatMap((g) => g.list.map((m) => m.model_id)),
    [modelGroup]
  );

  useImperativeHandle(ref, () => ({
    showModal: () => {
      setVisible(true);
      setSearchValue('');
      setCheckedKeys(allModelIds);
    },
  }));

  const treeData: DataNode[] = useMemo(() => {
    const lower = searchValue.trim().toLowerCase();
    return modelGroup
      .map((g) => {
        const children = g.list
          .filter((m) => !lower || m.model_name.toLowerCase().includes(lower))
          .map((m) => ({ title: m.model_name, key: m.model_id }));
        if (!children.length) return null;
        return {
          title: g.classification_name,
          key: `cls:${g.classification_id}`,
          children,
        } as DataNode;
      })
      .filter(Boolean) as DataNode[];
  }, [modelGroup, searchValue]);

  const selectedModelIds = useMemo(
    () => checkedKeys.filter((k) => !k.startsWith('cls:')),
    [checkedKeys]
  );

  const onCheck = (checked: any) => {
    const keys = Array.isArray(checked) ? checked : checked?.checked || [];
    setCheckedKeys(keys as string[]);
  };

  const selectAll = () => setCheckedKeys(allModelIds);
  const clearAll = () => setCheckedKeys([]);

  const handleExport = async () => {
    if (!selectedModelIds.length) {
      message.warning(t('Model.exportSelectAtLeastOne'));
      return;
    }
    setExportLoading(true);
    try {
      await exportModelConfig(tokenRef.current, selectedModelIds);
      handleCancel();
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setExportLoading(false);
    }
  };

  const handleCancel = () => {
    setVisible(false);
  };

  return (
    <OperateModal
      title={t('Model.exportModelConfig')}
      visible={visible}
      onCancel={handleCancel}
      footer={
        <div>
          <Button
            className="mr-[10px]"
            type="primary"
            loading={exportLoading}
            disabled={!selectedModelIds.length}
            onClick={handleExport}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <div>
        <div className="flex items-center mb-[10px]">
          <Input.Search
            allowClear
            className="flex-1 mr-[8px]"
            placeholder={t('Model.searchModelPlaceholder')}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
          />
          <Button size="small" type="link" onClick={selectAll}>
            {t('selectAll')}
          </Button>
          <Button size="small" type="link" onClick={clearAll}>
            {t('clear')}
          </Button>
        </div>
        <div className="max-h-[420px] overflow-auto">
          <Tree
            checkable
            checkStrictly={false}
            checkedKeys={checkedKeys}
            onCheck={onCheck}
            treeData={treeData}
            defaultExpandAll
            selectable={false}
          />
        </div>
      </div>
    </OperateModal>
  );
});

ExportModelConfigModal.displayName = 'ExportModelConfigModal';
export default ExportModelConfigModal;
