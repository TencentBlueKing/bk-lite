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
  HOST_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { formatTaskValues, buildCredential } from '../hooks/formatTaskValues';
import { Form, Spin, Input, Collapse, InputNumber } from 'antd';

interface HostTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const HostTask: React.FC<HostTaskFormProps> = ({
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
    initialValues: HOST_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const baseData = formatTaskValues({
        values,
        baseRef,
        selectedNode,
        modelItem,
        modelId,
        formatCycleValue,
      });

      const collectType = baseRef.current?.collectionType;
      const ipRange = values.ipRange?.length ? values.ipRange : undefined;
      const selectedData = baseRef.current?.selectedData;

      let instanceData;
      if (collectType === 'ip') {
        instanceData = {
          ip_range: ipRange.join('-'),
          instances: [],
        };
      } else {
        instanceData = {
          ip_range: '',
          instances: selectedData || [],
        };
      }

      return {
        ...baseData,
        ...instanceData,
        credential: buildCredential(
          {
            username: 'username',
            password: 'password',
            port: 'port',
          },
          values
        ),
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
          organization: values.team || [],
          username: values.credential?.username,
          password: PASSWORD_PLACEHOLDER,
          port: values.credential.port,
          accessPointId: values.access_point?.[0]?.id,
        });
      } else {
        form.setFieldsValue(HOST_FORM_INITIAL_VALUES);
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
        initialValues={HOST_FORM_INITIAL_VALUES}
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
            defaultValue: 60,
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
                label={t('user')}
                name="username"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input placeholder={t('common.inputTip')} />
              </Form.Item>

              <Form.Item
                label={t('password')}
                name="password"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input.Password
                  placeholder={t('common.inputTip')}
                  onFocus={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (value === PASSWORD_PLACEHOLDER) {
                      form.setFieldValue('password', '');
                    }
                  }}
                  onBlur={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (!value || value.trim() === '') {
                      form.setFieldValue('password', PASSWORD_PLACEHOLDER);
                    }
                  }}
                />
              </Form.Item>

              <Form.Item
                label={t('Collection.port')}
                name="port"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <InputNumber
                  min={1}
                  max={65535}
                  className="w-32"
                  placeholder="22"
                />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default HostTask;
