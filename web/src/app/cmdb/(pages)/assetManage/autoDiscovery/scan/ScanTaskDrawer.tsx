'use client';

import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Drawer, Form, Input, InputNumber, Select, Spin, message } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import GroupTreeSelector from '@/components/group-tree-select';
import IpRangeInput from '@/app/cmdb/components/ipInput';
import { isIpRangeOrderValid, isIpRangeWithinLimit } from '@/app/cmdb/components/ipInput/ipRangeLimits';
import CredentialPoolEditor, {
  type CredentialPoolEditorProps,
} from '@/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor';
import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import { useCollectApi, useScanApi } from '@/app/cmdb/api';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import {
  buildScanTaskSubmitMeta,
  hasScanCloudRegion,
  mapScanDetailToFormValues,
} from './scanTaskForm';

const SCAN_CREDENTIAL_LIMIT = 32;

export const SCAN_FAMILIES: Array<{
  modelId: string;
  labelKey: string;
  shape: CredentialPoolEditorProps['credentialShape'];
}> = [
  { modelId: 'network', labelKey: 'Scan.familyNetwork', shape: 'snmp' },
  { modelId: 'host', labelKey: 'Scan.familyHost', shape: 'ssh' },
  { modelId: 'physcial_server', labelKey: 'Scan.familyPhysical', shape: 'ipmi' },
  { modelId: 'database', labelKey: 'Scan.familyDatabase', shape: 'sql' },
  { modelId: 'influxdb', labelKey: 'Scan.familyInfluxdb', shape: 'influxdb' },
];

interface ScanTaskDrawerProps {
  open: boolean;
  editId: number | null;
  onClose: () => void;
  onSuccess: () => void;
}

const sanitizePool = (pool: CredentialPoolItem[] = []) =>
  pool
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const next: CredentialPoolItem = { ...item };
      delete next._client_id;
      Object.keys(next).forEach((key) => {
        if (next[key] === PASSWORD_PLACEHOLDER || next[key] === undefined) {
          delete next[key];
        }
      });
      return next;
    });

function IpRangeAdapter({
  value,
  onChange,
}: {
  value?: { begin?: string; end?: string } | string[];
  onChange?: (value: { begin: string; end: string }) => void;
}) {
  const ipValue = Array.isArray(value)
    ? value
    : [value?.begin || '', value?.end || ''];
  return (
    <IpRangeInput
      value={ipValue}
      onChange={(next) => onChange?.({ begin: next[0] || '', end: next[1] || '' })}
    />
  );
}

const FormSectionHeader: React.FC<{ title: string }> = ({ title }) => (
  <div className="mb-4 flex items-center gap-2 border-b border-[var(--color-border-2)] pb-2 pt-1">
    <div className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
    <span className="text-sm font-semibold text-[var(--color-text-1)]">{title}</span>
  </div>
);

const ScanTaskDrawer: React.FC<ScanTaskDrawerProps> = ({
  open,
  editId,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { getCollectNodes } = useCollectApi();
  const { getScanDetail, createScan, updateScan } = useScanApi();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [formReady, setFormReady] = useState(false);
  const [savedAccessPoint, setSavedAccessPoint] = useState<Record<string, unknown> | null>(null);
  const [savedCloudRegion, setSavedCloudRegion] = useState<unknown>();
  const [accessPoints, setAccessPoints] = useState<
    { label: string; value: string; origin: Record<string, unknown> }[]
  >([]);
  const families: string[] = Form.useWatch('families', form) || [];

  useEffect(() => {
    if (!open) {
      setFormReady(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setFormReady(false);
      try {
        const [nodesRes, detail] = await Promise.all([
          getCollectNodes({
            page: 1,
            page_size: 10000,
            name: '',
          }),
          editId ? getScanDetail(editId) : Promise.resolve(null),
        ]);
        if (cancelled) {
          return;
        }
        setAccessPoints(
          nodesRes.nodes
            ?.filter((node: { node_type?: string }) => node?.node_type === 'container')
            .map((node: { name: string; id: string }) => ({
              label: node.name,
              value: node.id,
              origin: node,
            })) || []
        );
        if (!editId || !detail) {
          setSavedAccessPoint(null);
          setSavedCloudRegion(undefined);
          form.setFieldsValue({
            name: '',
            team: selectedGroup?.id ? [selectedGroup.id] : [],
            ipRanges: [{ begin: '', end: '' }],
            families: [],
            credentials: {},
            accessPointId: undefined,
            timeout: 0,
          });
          return;
        }
        setSavedAccessPoint(detail.access_point?.[0] || null);
        setSavedCloudRegion(detail.cloud_region);
        form.setFieldsValue(mapScanDetailToFormValues(detail));
      } catch (error) {
        console.error(error);
        message.error(t('loadFailed'));
      } finally {
        if (!cancelled) {
          setFormReady(true);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [open, editId, selectedGroup?.id]);

  const handleFinish = async (values: Record<string, any>) => {
    const ranges = (values.ipRanges || [])
      .map((item: { begin?: string; end?: string } | string[]) => {
        if (Array.isArray(item)) {
          return { begin: item[0], end: item[1] };
        }
        return { begin: item.begin, end: item.end };
      })
      .filter((item: { begin?: string; end?: string }) => item.begin && item.end);
    if (!ranges.length) {
      message.error(t('Scan.ipRanges'));
      return;
    }
    for (const range of ranges) {
      if (!isIpRangeOrderValid(range.begin, range.end) || !isIpRangeWithinLimit(range.begin, range.end)) {
        message.error(t('Scan.ipRanges'));
        return;
      }
    }
    const selectedFamilies: string[] = values.families || [];
    if (!selectedFamilies.length) {
      message.error(t('Scan.families'));
      return;
    }
    const includeHost = selectedFamilies.includes('host');
    const submitMeta = buildScanTaskSubmitMeta({
      accessPointId: values.accessPointId,
      accessPoints,
      fallbackAccessPoint: savedAccessPoint,
      includeHost,
      existingCloudRegion: savedCloudRegion,
      timeout: values.timeout,
    });
    const credentials: Record<string, CredentialPoolItem[]> = {};
    selectedFamilies.forEach((modelId) => {
      const pool = sanitizePool(values.credentials?.[modelId] || []);
      if (modelId === 'database') {
        pool.forEach((item) => {
          delete item.port;
        });
      }
      credentials[modelId] = pool;
    });
    const payload = {
      name: values.name,
      team: values.team,
      access_point: submitMeta.access_point,
      ip_ranges: ranges,
      families: selectedFamilies,
      credentials,
      timeout: submitMeta.timeout,
      auto_push_monitor: false,
      auto_generate_collect: false,
      cloud_region: submitMeta.cloud_region,
    };
    if (includeHost && !hasScanCloudRegion(payload.cloud_region)) {
      message.error(t('Scan.cloudRegionRequired'));
      return;
    }
    setSubmitting(true);
    try {
      if (editId) {
        await updateScan(editId, payload);
        message.success(t('successfullyModified'));
      } else {
        await createScan(payload);
        message.success(t('successfullyAdded'));
      }
      onSuccess();
      onClose();
    } catch (error) {
      console.error(error);
      message.error(t('loadFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title={editId ? t('Scan.editTask') : t('Scan.addTask')}
      open={open}
      width={960}
      destroyOnClose
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            type="primary"
            loading={submitting || !formReady}
            disabled={!formReady}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
        </div>
      }
    >
      <Spin spinning={!formReady}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleFinish}
          initialValues={{
            ipRanges: [{ begin: '', end: '' }],
          }}
          className="flex flex-col gap-6"
        >
          {/* Section 1: 基础信息 */}
          <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-2)] p-4 shadow-sm">
            <FormSectionHeader title={t('Scan.sectionBasic')} />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Form.Item
                label={t('Scan.taskName')}
                name="name"
                rules={[{ required: true, message: t('common.inputMsg') }]}
                className="md:col-span-2"
              >
                <Input placeholder={t('common.inputMsg')} />
              </Form.Item>
              <Form.Item
                label={t('organization')}
                name="team"
                rules={[{ required: true, message: t('common.selectTip') }]}
              >
                <GroupTreeSelector multiple placeholder={t('common.selectTip')} />
              </Form.Item>
              <Form.Item
                label={t('Collection.accessPoint')}
                name="accessPointId"
                rules={[{ required: true, message: t('common.selectTip') }]}
              >
                <Select options={accessPoints} placeholder={t('common.selectTip')} />
              </Form.Item>
              <Form.Item label={t('Collection.timeout')}>
                <div className="flex items-center gap-2">
                  <Form.Item name="timeout" noStyle>
                    <InputNumber min={0} className="w-32" />
                  </Form.Item>
                  <span className="text-xs text-[var(--color-text-3)]">{t('Scan.timeoutSeconds')}</span>
                </div>
              </Form.Item>
            </div>
          </div>

          {/* Section 2: 扫描范围与凭据 */}
          <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-2)] p-4 shadow-sm">
            <FormSectionHeader title={t('Scan.sectionScope')} />
            <Form.Item label={t('Scan.ipRanges')} required>
              <Form.List name="ipRanges">
                {(fields, { add, remove }) => (
                  <div className="flex flex-col gap-2.5">
                    {fields.map(({ key, name, ...restField }) => (
                      <div key={key} className="flex items-center gap-3">
                        <Form.Item {...restField} name={name} className="!mb-0 flex-1">
                          <IpRangeAdapter />
                        </Form.Item>
                        {fields.length > 1 ? (
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => remove(name)}
                          />
                        ) : null}
                      </div>
                    ))}
                    <div>
                      <Button
                        type="dashed"
                        icon={<PlusOutlined />}
                        onClick={() => add({ begin: '', end: '' })}
                        className="w-full"
                      >
                        {t('Scan.addRange')}
                      </Button>
                    </div>
                  </div>
                )}
              </Form.List>
            </Form.Item>

            <Form.Item
              label={t('Scan.families')}
              name="families"
              rules={[{ required: true, message: t('common.selectTip') }]}
            >
              <Checkbox.Group className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {SCAN_FAMILIES.map((family) => (
                  <div
                    key={family.modelId}
                    className="flex items-center rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3 py-2"
                  >
                    <Checkbox value={family.modelId} className="w-full">
                      <span className="text-sm">{t(family.labelKey)}</span>
                    </Checkbox>
                  </div>
                ))}
              </Checkbox.Group>
            </Form.Item>

            {SCAN_FAMILIES.filter((family) => families.includes(family.modelId)).map((family) => (
              <div
                key={family.modelId}
                className="mt-3 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3.5"
              >
                <Form.Item
                  label={
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-[var(--color-text-1)]">{t(family.labelKey)}</span>
                      {family.modelId === 'database' ? (
                        <span className="text-xs font-normal text-[var(--color-text-3)]">
                          （{t('Scan.databasePortHint')}）
                        </span>
                      ) : null}
                    </div>
                  }
                  name={['credentials', family.modelId]}
                  className="!mb-0"
                >
                  <CredentialPoolEditor
                    credentialShape={family.shape}
                    showPort={family.modelId !== 'database'}
                    maxCount={SCAN_CREDENTIAL_LIMIT}
                    editMode={Boolean(editId)}
                  />
                </Form.Item>
              </div>
            ))}
          </div>
        </Form>
      </Spin>
    </Drawer>
  );
};

export default ScanTaskDrawer;
