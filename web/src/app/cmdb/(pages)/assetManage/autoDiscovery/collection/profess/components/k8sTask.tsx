'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import styles from '../index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import { Form, Spin, Select, Input, Alert } from 'antd';
import {
  getCleanupFormValues,
  getCycleFormValues,
  useTaskForm,
} from '../hooks/useTaskForm';
import { K8S_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import useApiClient from '@/utils/request';
import {
  K8sDaemonSetTolerationsEditor,
  createK8sTolerationsEditorCopy,
  k8sTolerationRuleMessage,
  toRequestTolerations,
  validateK8sDaemonSetTolerations,
  type K8sDaemonSetToleration,
} from '@/app/monitor/components/k8s-collector-install-step';

const COLLECTOR_CLUSTER_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

interface K8sTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
  /**
   * 引导式向导回调：任务保存成功后，由外层接管后续步骤。
   * 返回 true 表示已接管，组件不再触发默认关闭。
   */
  onAfterSave?: (ctx: {
    collector_cluster_id: string;
    cloud_region_id: number | string;
    tolerations?: K8sDaemonSetToleration[] | null;
    values: any;
  }) => boolean | void | Promise<boolean | void>;
}

const K8sTaskForm: React.FC<K8sTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
  onAfterSave,
}) => {
  const { t } = useTranslation();
  const collectionFormLayout = useCollectionFormLayout();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { model_id: modelId } = modelItem;
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const { get } = useApiClient();
  const [cloudRegions, setCloudRegions] = useState<any[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // 复用 node_mgmt 的云区域接口（CMDB 与 monitor 同一基础设施来源）
        const data = await get('/node_mgmt/api/cloud_region/');
        if (!cancelled) {
          setCloudRegions(Array.isArray(data) ? data : data?.results || []);
        }
      } catch (e) {
        console.error('Failed to load cloud regions:', e);
      }
    })();
    return () => { cancelled = true; };
  }, []);

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
    initialValues: K8S_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    afterSubmitSuccess: onAfterSave
      ? async ({ values }) => {
        const result = await onAfterSave({
          collector_cluster_id: values.collector_cluster_id,
          cloud_region_id: values.cloud_region_id,
          tolerations: toRequestTolerations(values.tolerations),
          values,
        });
        return result === true;
      }
      : undefined,
    formatValues: (values) => {
      const instance = baseRef.current?.instOptions?.find(
        (item) => item.value === values.instUuid
      );

      // collector_cluster_id 和 cloud_region_id 写入到 instance + params，
      // 后端 BaseCollect.build_plugin_kwargs() 会优先从 instance 读取。
      const enrichedInstance = instance?.origin
        ? {
          ...instance.origin,
          collector_cluster_id: values.collector_cluster_id,
        }
        : undefined;

      const baseData = formatTaskValues({
        values,
        baseRef,
        selectedNode,
        modelItem,
        modelId,
        formatCycleValue,
      });

      return {
        ...baseData,
        instances: enrichedInstance ? [enrichedInstance] : [],
        input_method: 0,
        ip_range: '',
        params: {
          ...baseData.params,
          collector_cluster_id: values.collector_cluster_id,
          cloud_region_id: values.cloud_region_id,
          tolerations: toRequestTolerations(values.tolerations),
        },
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...getCycleFormValues(values),
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    instUuid: values.instances?.[0]?.inst_uuid,
    ip_precheck: Boolean(values.params?.ip_precheck),
    collector_cluster_id:
      values.instances?.[0]?.collector_cluster_id ??
      values.params?.collector_cluster_id ??
      '',
    cloud_region_id: values.params?.cloud_region_id,
    tolerations:
      values.params?.tolerations === undefined
        ? null
        : values.params?.tolerations,
    timeout: values.timeout,
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        form.setFieldsValue(buildFormValues(values, true));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        form.setFieldsValue(buildFormValues(values, false));
      } else {
        form.setFieldsValue(K8S_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  return (
    <Spin spinning={loading} wrapperClassName={styles.k8sTaskSpin}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={K8S_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('common.select')} ${t('Collection.k8sTask.selectK8S')}`}
          submitText={onAfterSave ? `${t('common.next')} →` : undefined}
          showTimeout={false}
          showIpPrecheck={false}
        >
          <Form.Item
            label={t('Collection.k8sTask.collectorClusterId') || 'Cluster ID'}
            name="collector_cluster_id"
            rules={[
              { required: true, message: t('common.required') },
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  return COLLECTOR_CLUSTER_ID_PATTERN.test(value)
                    ? Promise.resolve()
                    : Promise.reject(
                      new Error(
                        t('Collection.k8sTask.collectorClusterIdInvalid') ||
                        'Only English letters, digits, underscores and hyphens are allowed'
                      )
                    );
                },
              },
            ]}
            extra={t('Collection.k8sTask.collectorClusterIdDesc') ||
              'Important: Do not modify after creation, or deployed collectors will fail to match.'}
          >
            <Input placeholder="e.g. prod-cluster-1" />
          </Form.Item>
          <Form.Item
            label={t('Collection.k8sTask.cloudRegion') || 'Cloud Region'}
            name="cloud_region_id"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              placeholder={t('common.selectTip')}
              options={(cloudRegions || []).map((r: any) => ({
                value: r.id,
                label: r.display_name || r.name,
              }))}
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            className="mb-4"
            message={
              t('Collection.k8sTask.singleNodeTaintPrecondition') ||
              'On a single-node cluster that keeps the control-plane taint, central Deployments stay Pending. Administrators should remove that taint. Collector Deployments never receive tolerations.'
            }
          />
          <Form.Item
            label={t('Collection.k8sTask.taintTolerations') || 'Taint Tolerations'}
            name="tolerations"
            extra={t('Collection.k8sTask.taintTolerationsDesc')}
            rules={[
              {
                validator: (_, value) => {
                  const code = validateK8sDaemonSetTolerations(value);
                  if (!code) return Promise.resolve();
                  return Promise.reject(
                    new Error(
                      k8sTolerationRuleMessage(
                        t,
                        'Collection.k8sTask',
                        code
                      ) || code
                    )
                  );
                },
              },
            ]}
          >
            <K8sDaemonSetTolerationsEditor
              copy={createK8sTolerationsEditorCopy(t, 'Collection.k8sTask')}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default K8sTaskForm;
