'use client';

import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Drawer, Form, Input, InputNumber, Select, Spin, Switch, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
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

const SCAN_CREDENTIAL_LIMIT = 32;

export const SCAN_FAMILIES: Array<{
  modelId: string;
  labelKey: string;
  shape: CredentialPoolEditorProps['credentialShape'];
}> = [
  { modelId: 'network', labelKey: 'Scan.familyNetwork', shape: 'snmp' },
  { modelId: 'host', labelKey: 'Scan.familyHost', shape: 'ssh' },
  { modelId: 'physcial_server', labelKey: 'Scan.familyPhysical', shape: 'ipmi' },
  { modelId: 'mysql', labelKey: 'Scan.familyMysql', shape: 'sql' },
  { modelId: 'postgresql', labelKey: 'Scan.familyPostgresql', shape: 'sql' },
  { modelId: 'mssql', labelKey: 'Scan.familyMssql', shape: 'sql' },
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
  const [detailLoading, setDetailLoading] = useState(false);
  const [accessPoints, setAccessPoints] = useState<
    { label: string; value: string; origin: Record<string, unknown> }[]
  >([]);
  const families: string[] = Form.useWatch('families', form) || [];

  useEffect(() => {
    if (!open) {
      return;
    }
    const load = async () => {
      try {
        const res = await getCollectNodes({
          page: 1,
          page_size: 10000,
          name: '',
        });
        setAccessPoints(
          res.nodes
            ?.filter((node: { node_type?: string }) => node?.node_type === 'container')
            .map((node: { name: string; id: string }) => ({
              label: node.name,
              value: node.id,
              origin: node,
            })) || []
        );
      } catch (error) {
        console.error(error);
      }
    };
    load();
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!editId) {
      setDetailLoading(false);
      form.setFieldsValue({
        name: '',
        team: selectedGroup?.id ? [selectedGroup.id] : [],
        ipRanges: [{ begin: '', end: '' }],
        families: [],
        credentials: {},
        accessPointId: undefined,
        timeout: 0,
        auto_push_monitor: false,
        auto_generate_collect: false,
      });
      return;
    }
    const loadDetail = async () => {
      setDetailLoading(true);
      try {
        const detail = await getScanDetail(editId);
        form.setFieldsValue({
          name: detail.name,
          team: detail.team,
          ipRanges: detail.ip_ranges?.length ? detail.ip_ranges : [{ begin: '', end: '' }],
          families: detail.families || [],
          credentials: detail.credentials || {},
          accessPointId: detail.access_point?.[0]?.id,
          timeout: detail.timeout || 0,
          auto_push_monitor: Boolean(detail.auto_push_monitor),
          auto_generate_collect: Boolean(detail.auto_generate_collect),
        });
      } catch (error) {
        console.error(error);
        message.error(t('loadFailed'));
      } finally {
        setDetailLoading(false);
      }
    };
    loadDetail();
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
    const accessPoint = accessPoints.find((item) => item.value === values.accessPointId);
    const origin = accessPoint?.origin || {};
    const credentials: Record<string, CredentialPoolItem[]> = {};
    selectedFamilies.forEach((modelId) => {
      credentials[modelId] = sanitizePool(values.credentials?.[modelId] || []);
    });
    const payload = {
      name: values.name,
      team: values.team,
      access_point: accessPoint ? [origin] : [],
      ip_ranges: ranges,
      families: selectedFamilies,
      credentials,
      timeout: values.timeout || 0,
      auto_push_monitor: Boolean(values.auto_push_monitor),
      auto_generate_collect: Boolean(values.auto_generate_collect),
      cloud_region: selectedFamilies.includes('host')
        ? origin.cloud_region || {
          id: origin.cloud_region_id,
          name: origin.cloud_region_name,
        }
        : {},
    };
    if (selectedFamilies.includes('host') && !payload.cloud_region) {
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
          <Button type="primary" loading={submitting || detailLoading} disabled={detailLoading} onClick={() => form.submit()}>
            {t('common.confirm')}
          </Button>
        </div>
      }
    >
      <Spin spinning={detailLoading}>
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        initialValues={{
          auto_push_monitor: false,
          auto_generate_collect: false,
          ipRanges: [{ begin: '', end: '' }],
        }}
      >
        <Form.Item
          label={t('Scan.taskName')}
          name="name"
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input />
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
        <Form.Item label={t('Scan.ipRanges')} required>
          <Form.List name="ipRanges">
            {(fields, { add, remove }) => (
              <div className="flex flex-col gap-3">
                {fields.map((field) => (
                  <div key={field.key} className="flex items-center gap-3">
                    <Form.Item {...field} className="mb-0">
                      <IpRangeAdapter />
                    </Form.Item>
                    {fields.length > 1 ? (
                      <Button type="link" onClick={() => remove(field.name)}>
                        {t('common.delete')}
                      </Button>
                    ) : null}
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ begin: '', end: '' })}>
                  {t('Scan.addRange')}
                </Button>
              </div>
            )}
          </Form.List>
        </Form.Item>
        <Form.Item
          label={t('Scan.families')}
          name="families"
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Checkbox.Group className="flex flex-col gap-2">
            {SCAN_FAMILIES.map((family) => (
              <Checkbox key={family.modelId} value={family.modelId}>
                {t(family.labelKey)}
              </Checkbox>
            ))}
          </Checkbox.Group>
        </Form.Item>
        {SCAN_FAMILIES.filter((family) => families.includes(family.modelId)).map((family) => (
          <Form.Item
            key={family.modelId}
            label={t(family.labelKey)}
            name={['credentials', family.modelId]}
          >
            <CredentialPoolEditor
              credentialShape={family.shape}
              maxCount={SCAN_CREDENTIAL_LIMIT}
              editMode={Boolean(editId)}
            />
          </Form.Item>
        ))}
        <Form.Item label={t('Collection.timeout')} name="timeout">
          <InputNumber min={0} className="w-40" />
        </Form.Item>
        <Form.Item label={t('Scan.autoPushMonitor')} name="auto_push_monitor" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label={t('Scan.autoGenerateCollect')} name="auto_generate_collect" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
      </Spin>
    </Drawer>
  );
};

export default ScanTaskDrawer;
