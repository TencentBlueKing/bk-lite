'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  buildSnmpTopologyParams,
  CYCLE_OPTIONS,
  getSnmpTopologyFormValues,
  recommendedTopologyIntervalMinutes,
  SNMP_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
  TOPOLOGY_FALLBACK_STRATEGY_OPTIONS,
  TOPOLOGY_PROTOCOL_OPTIONS,
} from '@/app/cmdb/constants/professCollection';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import {
  formatTaskValues,
  trimFormString,
  normalizeCredentialPool,
  buildCredentialPool,
} from '../hooks/formatTaskValues';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { Button, Form, InputNumber, Select, Spin, Switch, Tooltip } from 'antd';
import CredentialPoolEditor from './credentialPoolEditor';
import { buildSnmpCredentialHelp } from './credentialHelp';

const LONG_TOOLTIP_OVERLAY_STYLE = {
  maxWidth: 'min(520px, calc(100vw - 48px))',
};

interface SNMPTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const SNMPTask: React.FC<SNMPTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const collectionFormLayout = useCollectionFormLayout();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const { model_id: modelId } = modelItem;
  const initialFormValues = {
    ...SNMP_FORM_INITIAL_VALUES,
    credentialPool: [{ version: 'v2', snmp_port: '161' }],
  };

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
    initialValues: initialFormValues,
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
        credential: buildCredentialPool(values.credentialPool, (item) => {
          const version = item.version || 'v2';
          const community = trimFormString(item.community);
          const username = trimFormString(item.username);
          const authkey = trimFormString(item.authkey);
          const privkey = trimFormString(item.privkey);

          const credential: Record<string, any> = {
            version,
            snmp_port: item.snmp_port,
          };

          if (item.credential_id) {
            credential.credential_id = item.credential_id;
          }
          if (version !== 'v3' && community && community !== PASSWORD_PLACEHOLDER) {
            credential.community = community;
          }
          if (version === 'v3') {
            credential.level = item.level;
            credential.username = username;
            credential.integrity = item.integrity;
            if (authkey && authkey !== PASSWORD_PLACEHOLDER) {
              credential.authkey = authkey;
            }
            if (item.level === 'authPriv') {
              credential.privacy = item.privacy;
              if (privkey && privkey !== PASSWORD_PLACEHOLDER) {
                credential.privkey = privkey;
              }
            }
          }
          return credential;
        }),
        params: {
          ...baseData.params,
          ...buildSnmpTopologyParams(values),
        },
      };
    },
  });
  const hasNetworkTopo = Form.useWatch('hasNetworkTopo', form);
  const deviceCycleType = Form.useWatch('cycle', form);
  const deviceCycleMinutes = Form.useWatch('intervalValue', form);
  const topologyIntervalMode = Form.useWatch('topologyIntervalMode', form);
  const recommendedInterval =
    deviceCycleType === CYCLE_OPTIONS.INTERVAL &&
    Number(deviceCycleMinutes) > 0
      ? recommendedTopologyIntervalMinutes(Number(deviceCycleMinutes))
      : undefined;

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => {
    const credentialPool = normalizeCredentialPool(values.credential).map((item) => ({
      ...item,
      community: isCopy ? '' : PASSWORD_PLACEHOLDER,
      authkey: isCopy ? '' : PASSWORD_PLACEHOLDER,
      privkey: isCopy ? '' : PASSWORD_PLACEHOLDER,
    }));
    return {
      ...getCleanupFormValues(values),
      ...values,
      ...getSnmpTopologyFormValues(values.params, values.intervalValue),
      credentialPool,
      ipRange,
      taskName: isCopy ? '' : values.name,
      timeout: values.timeout,
      ip_precheck: Boolean(values.params?.ip_precheck),
      input_method: values.input_method,
      organization: values.team || [],
      accessPointId: values.access_point?.[0]?.id,
    };
  };

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }

        // 复制任务中回填表单数据（此时任务名称和密码为空，需要用户手动输入）
        form.setFieldsValue(buildFormValues(values, true, ipRange));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }

        // 编辑任务中回填表单数据
        form.setFieldsValue(buildFormValues(values, false, ipRange));
      } else {
        form.setFieldsValue(initialFormValues);
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  useEffect(() => {
    if (!hasNetworkTopo) {
      return;
    }

    if (recommendedInterval === undefined) {
      void form
        .validateFields(['topologyIntervalMinutes'])
        .catch(() => undefined);
      return;
    }

    const currentInterval = form.getFieldValue('topologyIntervalMinutes');
    if (currentInterval === undefined || currentInterval === null) {
      form.setFieldsValue({
        topologyIntervalMinutes: recommendedInterval,
        topologyIntervalMode: 'recommended',
      });
      return;
    }

    if (topologyIntervalMode === 'recommended') {
      form.setFieldValue('topologyIntervalMinutes', recommendedInterval);
      void form
        .validateFields(['topologyIntervalMinutes'])
        .catch(() => undefined);
      return;
    }

    void form
      .validateFields(['topologyIntervalMinutes'])
      .catch(() => undefined);
  }, [
    deviceCycleMinutes,
    deviceCycleType,
    form,
    hasNetworkTopo,
    recommendedInterval,
    topologyIntervalMode,
  ]);

  const restoreRecommendedInterval = () => {
    if (recommendedInterval === undefined) {
      void form
        .validateFields(['topologyIntervalMinutes'])
        .catch(() => undefined);
      return;
    }
    form.setFieldsValue({
      topologyIntervalMinutes: recommendedInterval,
      topologyIntervalMode: 'recommended',
    });
    void form
      .validateFields(['topologyIntervalMinutes'])
      .catch(() => undefined);
  };

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={initialFormValues}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.chooseAsset')}`}
          timeoutProps={{
            min: 30,
            max: 86400,
            defaultValue: 30,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item
            label={t('Collection.SNMPTask.collectRelationships')}
            name="hasNetworkTopo"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.hasNetworkTopo !== currentValues.hasNetworkTopo
            }
          >
            {({ getFieldValue }) =>
              getFieldValue('hasNetworkTopo') ? (
                <>
                  <Form.Item
                    label={
                      <span>
                        {t('Collection.SNMPTask.topologyInterval')}
                        <Tooltip
                          overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                          title={t('Collection.SNMPTask.topologyIntervalHelp')}
                        >
                          <QuestionCircleOutlined
                            aria-label={t(
                              'Collection.SNMPTask.topologyIntervalHelp'
                            )}
                            className="ml-1 cursor-help text-gray-400"
                            tabIndex={0}
                          />
                        </Tooltip>
                      </span>
                    }
                    name="topologyIntervalMinutes"
                    dependencies={['hasNetworkTopo', 'cycle', 'intervalValue']}
                    extra={
                      <div className="flex items-center gap-2">
                        <span>
                          {recommendedInterval === undefined
                            ? t(
                              'Collection.SNMPTask.topologyIntervalRecommendedUnavailable'
                            )
                            : t(
                              'Collection.SNMPTask.topologyIntervalRecommended',
                              undefined,
                              { minutes: recommendedInterval }
                            )}
                        </span>
                        <Button
                          className="h-auto p-0"
                          type="link"
                          onClick={restoreRecommendedInterval}
                        >
                          {t('Collection.SNMPTask.restoreRecommended')}
                        </Button>
                      </div>
                    }
                    rules={[
                      {
                        validator: (_, value) => {
                          if (!form.getFieldValue('hasNetworkTopo')) {
                            return Promise.resolve();
                          }
                          if (
                            form.getFieldValue('cycle') !==
                            CYCLE_OPTIONS.INTERVAL
                          ) {
                            return Promise.reject(
                              new Error(
                                t(
                                  'Collection.SNMPTask.topologyIntervalCycleTypeError'
                                )
                              )
                            );
                          }
                          if (
                            !Number.isInteger(value) ||
                            Number(value) < 1
                          ) {
                            return Promise.reject(
                              new Error(
                                t(
                                  'Collection.SNMPTask.topologyIntervalMinError'
                                )
                              )
                            );
                          }
                          if (
                            Number(value) <
                            Number(form.getFieldValue('intervalValue'))
                          ) {
                            return Promise.reject(
                              new Error(
                                t(
                                  'Collection.SNMPTask.topologyIntervalDeviceCycleError'
                                )
                              )
                            );
                          }
                          return Promise.resolve();
                        },
                      },
                    ]}
                  >
                    <InputNumber
                      min={1}
                      precision={0}
                      addonAfter={t('Collection.SNMPTask.minuteUnit')}
                      placeholder={t('common.inputTip')}
                      className="w-48"
                      onChange={() =>
                        form.setFieldValue(
                          'topologyIntervalMode',
                          'custom'
                        )
                      }
                    />
                  </Form.Item>
                  <Form.Item name="topologyIntervalMode" hidden>
                    <input />
                  </Form.Item>
                  <Form.Item
                    label={
                      <span>
                        {t('Collection.SNMPTask.topologyTimeout')}
                        <Tooltip
                          title={t('Collection.SNMPTask.topologyTimeoutHelp')}
                        >
                          <QuestionCircleOutlined
                            aria-label={t(
                              'Collection.SNMPTask.topologyTimeoutHelp'
                            )}
                            className="ml-1 cursor-help text-gray-400"
                            tabIndex={0}
                          />
                        </Tooltip>
                      </span>
                    }
                    name="topologyTimeout"
                    rules={[
                      {
                        validator: (_, value) => {
                          if (!form.getFieldValue('hasNetworkTopo')) {
                            return Promise.resolve();
                          }
                          if (
                            !Number.isInteger(value) ||
                            Number(value) < 1 ||
                            Number(value) > 86400
                          ) {
                            return Promise.reject(
                              new Error(
                                t(
                                  'Collection.SNMPTask.topologyTimeoutRangeError'
                                )
                              )
                            );
                          }
                          return Promise.resolve();
                        },
                      },
                    ]}
                  >
                    <InputNumber
                      min={1}
                      max={86400}
                      precision={0}
                      addonAfter={t('Collection.k8sTask.second')}
                      placeholder={t('common.inputTip')}
                      className="w-48"
                    />
                  </Form.Item>
                  <Form.Item
                    label={
                      <span>
                        {t('Collection.SNMPTask.topologyProtocols')}
                        <Tooltip
                          overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                          title={t('Collection.SNMPTask.topologyProtocolsHelp')}
                        >
                          <QuestionCircleOutlined className="ml-1 cursor-help text-gray-400" />
                        </Tooltip>
                      </span>
                    }
                    name="topologyProtocols"
                  >
                    <Select
                      mode="multiple"
                      placeholder={t('common.selectTip')}
                      options={TOPOLOGY_PROTOCOL_OPTIONS.map((item) => ({
                        value: item.value,
                        label: t(item.labelKey),
                      }))}
                    />
                  </Form.Item>
                  <Form.Item
                    label={
                      <span>
                        {t('Collection.SNMPTask.topologyFallbackStrategy')}
                        <Tooltip
                          overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                          title={t(
                            'Collection.SNMPTask.topologyFallbackStrategyHelp'
                          )}
                        >
                          <QuestionCircleOutlined className="ml-1 cursor-help text-gray-400" />
                        </Tooltip>
                      </span>
                    }
                    name="topologyFallbackStrategy"
                  >
                    <Select
                      placeholder={t('common.selectTip')}
                      options={TOPOLOGY_FALLBACK_STRATEGY_OPTIONS.map((item) => ({
                        value: item.value,
                        label: t(item.labelKey),
                      }))}
                    />
                  </Form.Item>
                  <Form.Item
                    label={
                      <span>
                        {t('Collection.SNMPTask.minConfidence')}
                        <Tooltip
                          overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                          title={t('Collection.SNMPTask.minConfidenceHelp')}
                        >
                          <QuestionCircleOutlined className="ml-1 cursor-help text-gray-400" />
                        </Tooltip>
                      </span>
                    }
                    name="minConfidence"
                  >
                    <InputNumber
                      min={0}
                      max={1}
                      step={0.05}
                      precision={2}
                      placeholder={t('common.inputTip')}
                      className="w-32"
                    />
                  </Form.Item>
                </>
              ) : null
            }
          </Form.Item>

          <Form.Item name="credentialPool">
            <CredentialPoolEditor
              credentialShape="snmp"
              editMode={Boolean(editId)}
              credentialHelp={buildSnmpCredentialHelp(t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default SNMPTask;
