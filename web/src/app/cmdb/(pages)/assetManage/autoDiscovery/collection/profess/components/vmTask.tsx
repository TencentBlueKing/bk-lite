'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import styles from '../index.module.scss';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { CaretRightOutlined } from '@ant-design/icons';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { Form, Spin, Input, Switch, Collapse, InputNumber } from 'antd';

import {
  ENTER_TYPE,
  VM_FORM_INITIAL_VALUES,
  createTaskValidationRules,
} from '@/app/cmdb/constants/professCollection';

interface VMTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const VMTask: React.FC<VMTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null);
  const localeContext = useLocale();
  const { id: modelId } = modelItem;

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
    initialValues: VM_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const instance = baseRef.current?.instOptions.find(
        (item: any) => item.value === values.instId
      );
      const accessPoint = baseRef.current?.accessPoints.find(
        (item: any) => item.value === values.accessPointId
      );
      const driverType = selectedNode.tabItems?.find(
        (item) => item.id === modelId
      )?.type;

      return {
        name: values.taskName,
        instances: instance?.origin && [instance.origin],
        input_method: values.enterType === ENTER_TYPE.APPROVAL ? 1 : 0,
        access_point: accessPoint?.origin && [accessPoint.origin],
        timeout: values.timeout || 600,
        scan_cycle: formatCycleValue(values),
        model_id: modelId,
        driver_type: driverType,
        task_type: modelItem.task_type,
        credential: {
          username: values.username,
          password: values.password,
          port: values.port,
          ssl: values.sslVerify,
        },
      };
    },
  });

  const rules: any = React.useMemo(
    () => createTaskValidationRules({ t, form, taskType: 'vm' }),
    [t, form]
  );

  useEffect(() => {
    const initForm = async () => {
      if (editId) {
        const values = await fetchTaskDetail(editId);
        form.setFieldsValue({
          ...values,
          enterType:
            values.input_method === 0
              ? ENTER_TYPE.AUTOMATIC
              : ENTER_TYPE.APPROVAL,
          accessPointId: values.access_point?.[0]?.id,
          username: values.credential?.username,
          password: values.credential?.password,
          port: values.credential?.port,
          sslVerify: values.credential?.ssl,
        });
      } else {
        form.setFieldsValue(VM_FORM_INITIAL_VALUES);
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
        initialValues={VM_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('common.select')}${t('Collection.VMTask.chooseVCenter')}`}
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
                name="username"
                label={t('Collection.VMTask.username')}
                rules={rules.username}
              >
                <Input placeholder={t('common.inputMsg')} />
              </Form.Item>

              <Form.Item
                name="password"
                label={t('Collection.VMTask.password')}
                rules={rules.password}
              >
                <Input.Password placeholder={t('common.inputMsg')} />
              </Form.Item>

              <Form.Item
                name="port"
                label={t('Collection.VMTask.port')}
                rules={rules.port}
              >
                <InputNumber
                  min={1}
                  max={65535}
                  placeholder={t('common.inputMsg')}
                  className="w-32"
                  defaultValue={443}
                />
              </Form.Item>

              <Form.Item
                name="sslVerify"
                label={t('Collection.VMTask.sslVerify')}
                valuePropName="checked"
                className="mb-0"
                rules={rules.sslVerify}
              >
                <Switch defaultChecked />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default VMTask;
