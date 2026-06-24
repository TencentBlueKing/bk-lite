'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import {
  useTaskForm,
  getCleanupFormValues,
  getCycleFormValues,
} from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { CYCLE_OPTIONS } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import { useInstanceApi } from '@/app/cmdb/api';
import { Form, Spin, Alert, Radio, Input, Modal, Select } from 'antd';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';

// IP discovery: input_method = 2 (SUBNET)
const IP_TASK_INPUT_METHOD = 2;

// Aggregate address threshold: > /22 equivalent (1024 addresses)
const SUBNET_RANGE_WARN_THRESHOLD = 1024;

// Model ID for subnet instances in CMDB
const SUBNET_MODEL_ID = 'subnet';

interface IpTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const IP_TASK_INITIAL_VALUES = {
  cycle: CYCLE_OPTIONS.INTERVAL,
  intervalValue: 60,
  scanMethod: 'icmp',
  tcpPorts: '22,80,443,3389',
  timeout: 300,
  cleanupStrategy: 'no_cleanup',
  cleanupDays: 3,
};

/**
 * Derive a prefix length (0-32) from a subnet mask value that may be:
 *   - a numeric prefix length already (e.g. 24)
 *   - a dotted-decimal mask string (e.g. "255.255.255.0")
 * Returns NaN when the value cannot be parsed.
 */
function maskToPrefixlen(mask: string | number | undefined | null): number {
  if (mask === undefined || mask === null || mask === '') return NaN;
  const n = Number(mask);
  // Already a plain prefix length
  if (!Number.isNaN(n) && n >= 0 && n <= 32) return n;
  // Dotted-decimal form
  const str = String(mask).trim();
  if (str.includes('.')) {
    const parts = str.split('.').map(Number);
    if (parts.length !== 4 || parts.some(Number.isNaN)) return NaN;
    const bits = parts.reduce((acc, octet) => {
      let o = octet;
      let cnt = 0;
      while (o & 0x80) { cnt++; o = (o << 1) & 0xff; }
      return acc + cnt;
    }, 0);
    return bits;
  }
  return NaN;
}

/**
 * Compute total host-address count from a list of subnet instances.
 * Prefers `subnet_size` (the model's capacity field), then derives the count
 * from `subnet_mask` (supports dotted-decimal and prefix-length forms).
 * The raw instance may be nested under an `origin` key when coming from
 * the subnetOptions list. Falls back to 256 (/24) when no field is found.
 */
function computeTotalAddressCount(subnets: any[]): number {
  return subnets.reduce((total, s) => {
    // Unwrap origin if the option object wraps the raw instance
    const raw = s.origin ?? s;

    // Prefer explicit subnet_size capacity field
    const size = Number(raw.subnet_size ?? s.subnet_size);
    if (!Number.isNaN(size) && size > 0) {
      return total + size;
    }

    // Derive from subnet_mask (dotted-decimal or prefix-length)
    const mask = raw.subnet_mask ?? s.subnet_mask;
    const prefixlen = maskToPrefixlen(mask);
    if (!Number.isNaN(prefixlen) && prefixlen >= 0 && prefixlen <= 32) {
      return total + Math.pow(2, 32 - prefixlen);
    }

    // Unknown — conservatively count as /24 (256)
    return total + 256;
  }, 0);
}

const IpTask: React.FC<IpTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const localeContext = useLocale();
  const instanceApi = useInstanceApi();
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const { model_id: modelId } = modelItem;

  // Subnet multi-select state
  const [subnetOptions, setSubnetOptions] = useState<
    { label: string; value: number; prefixlen?: number; origin?: any }[]
  >([]);
  const [subnetLoading, setSubnetLoading] = useState(false);
  const [selectedSubnetIds, setSelectedSubnetIds] = useState<number[]>([]);
  const [selectedSubnetMeta, setSelectedSubnetMeta] = useState<any[]>([]);
  const [pendingSubmit, setPendingSubmit] = useState<null | (() => void)>(null);

  const fetchSubnets = useCallback(async () => {
    try {
      setSubnetLoading(true);
      const res = await instanceApi.searchInstances({
        model_id: SUBNET_MODEL_ID,
        page: 1,
        page_size: 10000,
      });
      const opts = (res.insts || []).map((s: any) => ({
        label: s.inst_name || s.subnet_address || s._id,
        value: Number(s._id),
        prefixlen: s.prefixlen ?? s.prefix_len,
        origin: s,
      }));
      setSubnetOptions(opts);
    } catch (err) {
      console.error('Failed to fetch subnets:', err);
    } finally {
      setSubnetLoading(false);
    }
  }, [instanceApi]);

  useEffect(() => {
    fetchSubnets();
  }, [fetchSubnets]);

  // Keep selectedSubnetMeta in sync with selectedSubnetIds for address counting
  useEffect(() => {
    const meta = selectedSubnetIds.map((id) => {
      const opt = subnetOptions.find((o) => o.value === id);
      return opt ?? { value: id };
    });
    setSelectedSubnetMeta(meta);
  }, [selectedSubnetIds, subnetOptions]);

  const {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    formatCycleValue,
    onFinish: baseOnFinish,
  } = useTaskForm({
    modelId,
    editId,
    initialValues: IP_TASK_INITIAL_VALUES,
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

      const scanMethod = values.scanMethod || 'icmp';
      const portsRaw: string = values.tcpPorts || '22,80,443,3389';
      const ports =
        scanMethod === 'tcp'
          ? portsRaw
            .split(',')
            .map((p) => Number(p.trim()))
            .filter((p) => !Number.isNaN(p) && p > 0)
          : [];

      return {
        ...baseData,
        task_type: 'ip',
        input_method: IP_TASK_INPUT_METHOD,
        instances: {
          subnet_ids: selectedSubnetIds,
          scan_method: scanMethod,
          ports,
        },
      };
    },
  });

  // Guard: confirm before submit if selected subnets exceed address threshold (D6)
  const handleFinish = (values: any) => {
    const totalAddresses = computeTotalAddressCount(selectedSubnetMeta);
    if (totalAddresses > SUBNET_RANGE_WARN_THRESHOLD) {
      setPendingSubmit(() => () => baseOnFinish(values));
    } else {
      baseOnFinish(values);
    }
  };

  // Build initial form values for copy/edit
  const buildFormValues = (values: any, isCopy: boolean) => {
    // Restore subnet_ids from instances field
    const subnetIds: number[] = Array.isArray(values.instances?.subnet_ids)
      ? values.instances.subnet_ids
      : [];
    setSelectedSubnetIds(subnetIds);

    const cycleFields = getCycleFormValues(values);
    const cleanupFields = getCleanupFormValues(values);
    return {
      ...cleanupFields,
      ...values,
      ...cycleFields,
      taskName: isCopy ? '' : values.name,
      organization: values.team || [],
      accessPointId: values.access_point?.[0]?.id,
      scanMethod: values.instances?.scan_method || 'icmp',
      tcpPorts: (values.instances?.ports || [22, 80, 443, 3389]).join(','),
      subnetIds,
    };
  };

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        form.setFieldsValue(buildFormValues(copyTaskData, true));
        setCopyTaskData(null);
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        if (values) {
          form.setFieldsValue(buildFormValues(values, false));
        }
      } else {
        form.setFieldsValue(IP_TASK_INITIAL_VALUES);
      }
    };
    initForm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, copyTaskData]);

  const scanMethodValue = Form.useWatch('scanMethod', form);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={handleFinish}
        initialValues={IP_TASK_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          showAdvanced={true}
          timeoutProps={{
            min: 0,
            defaultValue: 300,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          {/* Security warning — always visible */}
          <Alert
            className="mb-4"
            type="warning"
            showIcon
            message={t('Collection.IPTask.securityWarning')}
          />

          {/* Subnet multi-select */}
          <Form.Item
            label={t('Collection.IPTask.chooseSubnet')}
            name="subnetIds"
            required
            rules={[
              {
                validator: () => {
                  if (selectedSubnetIds.length === 0) {
                    return Promise.reject(
                      new Error(
                        t('common.inputMsg') + t('Collection.IPTask.chooseSubnet')
                      )
                    );
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <Select
              mode="multiple"
              loading={subnetLoading}
              options={subnetOptions}
              value={selectedSubnetIds}
              onChange={(ids: number[]) => {
                setSelectedSubnetIds(ids);
                form.setFieldValue('subnetIds', ids);
              }}
              placeholder={t('common.selectTip')}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              style={{ width: '100%' }}
            />
          </Form.Item>

          {/* Scan method */}
          <Form.Item
            label={t('Collection.IPTask.scanMethod')}
            name="scanMethod"
            required
          >
            <Radio.Group>
              <Radio value="icmp">ICMP</Radio>
              <Radio value="tcp">TCP</Radio>
            </Radio.Group>
          </Form.Item>

          {/* TCP ports — only visible when TCP is selected */}
          {scanMethodValue === 'tcp' && (
            <Form.Item
              label={t('Collection.IPTask.tcpPorts')}
              name="tcpPorts"
              required
              rules={[
                {
                  required: true,
                  message:
                    t('common.inputMsg') + t('Collection.IPTask.tcpPorts'),
                },
                {
                  validator: (_, value: string) => {
                    if (!value) return Promise.resolve();
                    const ports = value
                      .split(',')
                      .map((p) => Number(p.trim()))
                      .filter(Boolean);
                    if (
                      ports.length === 0 ||
                      ports.some((p) => Number.isNaN(p) || p < 1 || p > 65535)
                    ) {
                      return Promise.reject(
                        new Error(t('Collection.IPTask.tcpPortsInvalid'))
                      );
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <Input
                style={{ width: 300 }}
                placeholder="22,80,443,3389"
              />
            </Form.Item>
          )}
        </BaseTaskForm>
      </Form>

      {/* Range guard confirmation modal (D6) */}
      <Modal
        open={pendingSubmit !== null}
        title={t('Collection.IPTask.rangeGuardTitle')}
        okText={t('Collection.confirm')}
        cancelText={t('Collection.cancel')}
        onOk={() => {
          if (pendingSubmit) {
            pendingSubmit();
          }
          setPendingSubmit(null);
        }}
        onCancel={() => setPendingSubmit(null)}
      >
        <p>{t('Collection.IPTask.rangeGuardContent')}</p>
      </Modal>
    </Spin>
  );
};

export default IpTask;
