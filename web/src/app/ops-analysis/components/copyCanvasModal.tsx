'use client';

import React, { useEffect, useMemo } from 'react';
import { Form, Modal, Select, TreeSelect } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import type { DirItem } from '@/app/ops-analysis/types';
import {
  buildCopyDirectoryTree,
  collectDirectoryChainGroupIds,
  convergeCopyGroups,
  defaultCopyGroups,
  filterGroupTreeByAllowedIds,
} from '@/app/ops-analysis/utils/canvasDirectoryCopy';

const popupContainer = () => document.body;

interface CopyCanvasModalProps {
  open: boolean;
  directories: DirItem[];
  currentGroupId?: number | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onOk: (values: { directory: number; groups: number[] }) => Promise<void> | void;
}

const CopyCanvasModal: React.FC<CopyCanvasModalProps> = ({
  open,
  directories,
  currentGroupId,
  confirmLoading = false,
  onCancel,
  onOk,
}) => {
  const [form] = Form.useForm<{ directory?: number; groups?: number[] }>();
  const { t } = useTranslation();
  const { groupTree } = useUserInfoContext();
  const directoryId = Form.useWatch('directory', form);
  const allowedGroupIds = collectDirectoryChainGroupIds(directories, directoryId);
  const allowedGroupKey = allowedGroupIds.join(',');
  const directoryTree = useMemo(
    () => buildCopyDirectoryTree(directories),
    [directories],
  );
  const hasNestedDirectories = useMemo(
    () => directoryTree.some((node) => Boolean(node.children?.length)),
    [directoryTree],
  );
  const flatDirectoryOptions = useMemo(
    () =>
      directoryTree.map((node) => ({
        label: node.title,
        value: node.value,
        disabled: node.disabled,
      })),
    [directoryTree],
  );
  const groupOptions = filterGroupTreeByAllowedIds(
    convertGroupTreeToTreeSelectData(groupTree || []),
    allowedGroupIds,
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
  }, [open, form]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const nextGroups = directoryId
      ? convergeCopyGroups(form.getFieldValue('groups'), allowedGroupIds, currentGroupId)
      : defaultCopyGroups([], currentGroupId);
    form.setFieldValue('groups', nextGroups);
  }, [allowedGroupKey, currentGroupId, directoryId, form, open]);

  const handleOk = async () => {
    const values = await form.validateFields();
    await onOk({
      directory: Number(values.directory),
      groups: values.groups || [],
    });
  };

  return (
    <Modal
      title={t('common.copy')}
      open={open}
      centered
      confirmLoading={confirmLoading}
      onCancel={onCancel}
      onOk={handleOk}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="directory"
          label={t('opsAnalysisSidebar.copyTargetDirectory')}
          rules={[
            {
              required: true,
              message: `${t('common.selectMsg')}${t('opsAnalysisSidebar.copyTargetDirectory')}`,
            },
          ]}
        >
          {hasNestedDirectories ? (
            <TreeSelect
              treeData={directoryTree}
              placeholder={`${t('common.selectMsg')}${t('opsAnalysisSidebar.copyTargetDirectory')}`}
              treeDefaultExpandAll
              showSearch
              allowClear
              treeNodeFilterProp="title"
              className="w-full"
              popupMatchSelectWidth
              getPopupContainer={popupContainer}
            />
          ) : (
            <Select
              options={flatDirectoryOptions}
              placeholder={`${t('common.selectMsg')}${t('opsAnalysisSidebar.copyTargetDirectory')}`}
              showSearch
              allowClear
              optionFilterProp="label"
              className="w-full"
              popupMatchSelectWidth
              getPopupContainer={popupContainer}
            />
          )}
        </Form.Item>
        <Form.Item
          name="groups"
          label={t('common.group')}
          rules={[
            {
              required: true,
              message: `${t('common.selectMsg')}${t('common.group')}`,
            },
          ]}
        >
          <GroupTreeSelect
            treeData={groupOptions}
            placeholder={`${t('common.selectMsg')}${t('common.group')}`}
            multiple
            mode="ownership"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CopyCanvasModal;
