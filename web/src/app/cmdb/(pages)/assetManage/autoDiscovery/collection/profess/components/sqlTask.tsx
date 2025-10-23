'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import styles from '../index.module.scss';
import { CaretRightOutlined } from '@ant-design/icons';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  ENTER_TYPE,
  SQL_FORM_INITIAL_VALUES,
} from '@/app/cmdb/constants/professCollection';
import { Form, Spin, Input, Collapse, InputNumber } from 'antd';

interface SQLTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const SQLTask: React.FC<SQLTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null);
  const localeContext = useLocale();
  const { model_id: modelId } = modelItem;

  const {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    formatCycleValue,
    onFinish,
  } = useTaskForm({
    modelId,
    editId,
    initialValues: SQL_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const instance = baseRef.current?.selectedData;
      const collectType = baseRef.current?.collectionType;
      const ipRange = values.ipRange?.length ? values.ipRange : undefined;
      const driverType = selectedNode.tabItems?.find(
        (item) => item.model_id === modelId
      )?.type;

      const accessPoint = baseRef.current?.accessPoints.find(
        (item: any) => item.value === values.accessPointId
      );
      return {
        name: values.taskName,
        input_method: values.enterType === ENTER_TYPE.APPROVAL ? 1 : 0,
        access_point: accessPoint?.origin && [accessPoint.origin],
        timeout: values.timeout || 600,
        scan_cycle: formatCycleValue(values),
        model_id: modelId,
        driver_type: driverType,
        task_type: modelItem.task_type,
        accessPointId: values.access_point?.[0]?.id,
        credential: {
          user: values.user,
          password: values.password,
          port: values.port,
        },
        ...(collectType === 'ip'
          ? {
            ip_range: ipRange.join('-'),
            instances: [],
            params: {
              organization: [values.organization?.[0]],
            },
          } : { 
            ip_range: '',
            instances: instance || [] 
          }),
      };
    },
  });

  useEffect(() => {
    const initForm = async () => {
      if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }
        form.setFieldsValue({
          ipRange,
          ...values,
          ...values.credential,
          organization: values.params?.organization,
          accessPointId: values.access_point?.[0]?.id,
        });
      } else {
        form.setFieldsValue(SQL_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId]);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={SQL_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.chooseAsset')}`}
          timeoutProps={{
            min: 0,
            defaultValue: 600,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Collapse
            ghost
            defaultActiveKey={['credential']}
            expandIcon={({ isActive }) => (
              <CaretRightOutlined
                rotate={isActive ? 90 : 0}
                className="text-base"
              />
            )}
          >
            <Collapse.Panel
              header={
                <div className={styles.panelHeader}>
                  {t('Collection.credential')}
                </div>
              }
              key="credential"
            >
              <Form.Item
                label={t('Collection.VMTask.username')}
                name="user"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input placeholder={t('common.inputTip')} />
              </Form.Item>

              <Form.Item
                label={t('Collection.VMTask.password')}
                name="password"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input.Password placeholder={t('common.inputTip')} />
              </Form.Item>

              <Form.Item
                label={t('Collection.port')}
                name="port"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <InputNumber min={1} max={65535} className="w-32" />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default SQLTask;
