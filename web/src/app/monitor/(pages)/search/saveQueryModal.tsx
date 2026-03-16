'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
  useEffect
} from 'react';
import { Button, Form, message, Input } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useSearchApi from '@/app/monitor/api/search';
import {
  QueryGroup,
  QueryGroupData,
  SaveQueryModalRef,
  SaveQueryModalProps
} from '@/app/monitor/types/search';
import GroupTreeSelector from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import OperateModal from '@/components/operate-modal';

/**
 * 将前端 QueryGroup 转换为后端 QueryGroupData 格式
 */
const transformToBackendFormat = (groups: QueryGroup[]): QueryGroupData[] => {
  return groups.map((group) => ({
    id: group.id,
    name: group.name,
    object: group.object,
    instance_ids: group.instanceIds,
    metric: group.metric,
    aggregation: group.aggregation,
    conditions: group.conditions
  }));
};

const SaveQueryModal = forwardRef<SaveQueryModalRef, SaveQueryModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { selectedGroup } = useUserInfoContext();
    const { saveMonitorCondition } = useSearchApi();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [queryGroups, setQueryGroups] = useState<QueryGroup[]>([]);

    useImperativeHandle(ref, () => ({
      showModal: (groups: QueryGroup[]) => {
        setQueryGroups(groups);
        setVisible(true);
      }
    }));

    useEffect(() => {
      if (visible) {
        const defaultOrganizations = selectedGroup?.id
          ? [Number(selectedGroup.id)]
          : [];
        setTimeout(() => {
          formRef.current?.setFieldsValue({
            name: undefined,
            organizations: defaultOrganizations
          });
        }, 0);
      }
    }, [visible, selectedGroup]);

    const handleSubmit = async () => {
      try {
        const values = await formRef.current?.validateFields();
        setConfirmLoading(true);

        const queryGroupsData = transformToBackendFormat(queryGroups);

        await saveMonitorCondition({
          name: values.name,
          organizations: values.organizations,
          condition: queryGroupsData
        });
        message.success(t('common.successfullyAdded'));
        handleCancel();
        onSuccess?.();
      } catch (error) {
        console.error(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
    };

    return (
      <OperateModal
        title={t('monitor.search.saveQuery')}
        open={visible}
        width={500}
        destroyOnClose
        onCancel={handleCancel}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            <Button
              type="primary"
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
          </div>
        }
      >
        <Form ref={formRef} layout="vertical" className="mt-4">
          <Form.Item
            label={t('common.name')}
            name="name"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input placeholder={t('monitor.search.queryNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            label={t('monitor.group')}
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

SaveQueryModal.displayName = 'SaveQueryModal';
export default SaveQueryModal;
