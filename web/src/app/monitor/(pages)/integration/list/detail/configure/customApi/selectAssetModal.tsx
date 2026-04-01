'use client';

import React, {
  forwardRef,
  useImperativeHandle,
  useState,
  useMemo,
  useRef,
  useEffect
} from 'react';
import { Button, Input, Space } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { PushAccessInstanceItem } from '@/app/monitor/types/integration';
import { useCopy } from '@/hooks/useCopy';
import useMonitorApi from '@/app/monitor/api';

interface ModalConfig {
  instanceIdKeys: string[];
  selectedInstanceIds: React.Key[];
  organizationNameMap: Map<string, string>;
  objectId: number;
  selectedOrganization?: number;
}

export interface SelectAssetModalRef {
  showModal: (config: ModalConfig) => void;
}

interface SelectAssetModalProps {
  onConfirm: (selectedIds: React.Key[]) => void;
}

const buildInstanceIdentityLabel = (
  instance: PushAccessInstanceItem,
  instanceIdKeys: string[]
) => {
  const parseInternalInstanceId = (
    internalInstanceId: string,
    keys: string[]
  ) => {
    const actualKeys = keys?.length ? keys : ['instance_id'];
    const rawDimensions: Record<string, string> = {};

    if (!internalInstanceId) {
      return rawDimensions;
    }

    const quotedValues = Array.from(
      internalInstanceId.matchAll(/'([^']*)'|"([^"]*)"/g)
    ).map((match) => match[1] ?? match[2] ?? '');

    const values = quotedValues.length ? quotedValues : [internalInstanceId];

    actualKeys.forEach((key, index) => {
      rawDimensions[key] = values[index] || '';
    });

    return rawDimensions;
  };

  const rawInstance =
    instance.raw_instance ||
    parseInternalInstanceId(instance.instance_id || '', instanceIdKeys);
  const keys = instanceIdKeys?.length ? instanceIdKeys : ['instance_id'];
  return keys.map((key) => rawInstance[key] || '--').join(' / ');
};

const SelectAssetModal = forwardRef<SelectAssetModalRef, SelectAssetModalProps>(
  ({ onConfirm }, ref) => {
    const { t } = useTranslation();
    const { copy } = useCopy();
    const { getInstanceList } = useMonitorApi();
    const getInstanceListRef = useRef(getInstanceList);
    getInstanceListRef.current = getInstanceList;

    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [instanceIdKeys, setInstanceIdKeys] = useState<string[]>([
      'instance_id'
    ]);
    const [availableInstances, setAvailableInstances] = useState<
      PushAccessInstanceItem[]
    >([]);
    const [draftSelectedInstanceIds, setDraftSelectedInstanceIds] = useState<
      React.Key[]
    >([]);
    const [organizationNameMap, setOrganizationNameMap] = useState<
      Map<string, string>
    >(new Map());
    const [assetKeyword, setAssetKeyword] = useState('');
    const [objectId, setObjectId] = useState(0);
    const [selectedOrganization, setSelectedOrganization] = useState<number>();

    // 弹窗打开时请求数据
    useEffect(() => {
      if (!visible || !objectId) return;

      const fetchInstances = async () => {
        setLoading(true);
        try {
          const data = await getInstanceListRef.current(objectId, {
            page_size: -1
          });
          const instances = data?.results || [];
          // Filter by organization
          const filtered = selectedOrganization
            ? instances.filter((item: PushAccessInstanceItem) => {
              const orgValues = item.organization || item.organizations || [];
              return orgValues
                .map(Number)
                .includes(Number(selectedOrganization));
            })
            : instances;
          setAvailableInstances(filtered);
        } finally {
          setLoading(false);
        }
      };

      fetchInstances();
    }, [visible, objectId, selectedOrganization]);

    useImperativeHandle(ref, () => ({
      showModal: (config: ModalConfig) => {
        setInstanceIdKeys(config.instanceIdKeys);
        setDraftSelectedInstanceIds(config.selectedInstanceIds);
        setOrganizationNameMap(config.organizationNameMap);
        setObjectId(config.objectId);
        setSelectedOrganization(config.selectedOrganization);
        setAssetKeyword('');
        setAvailableInstances([]);
        setVisible(true);
      }
    }));

    const selectableAssets = useMemo(() => {
      const keyword = assetKeyword.trim().toLowerCase();
      if (!keyword) return availableInstances;
      return availableInstances.filter((item) => {
        const name = String(item.instance_name || '').toLowerCase();
        const rawValues = Object.values(item.raw_instance || {})
          .map((value) => String(value).toLowerCase())
          .join(' ');
        return name.includes(keyword) || rawValues.includes(keyword);
      });
    }, [availableInstances, assetKeyword]);

    const handleConfirm = () => {
      onConfirm(draftSelectedInstanceIds);
      setVisible(false);
    };

    const handleCancel = () => {
      setVisible(false);
    };

    const renderOrganizationText = (record: PushAccessInstanceItem) => {
      const orgValues = record.organization || record.organizations || [];
      if (!orgValues.length) return '--';
      return orgValues
        .map(
          (item: string | number) =>
            organizationNameMap.get(String(item)) || item
        )
        .join(', ');
    };

    const columns = [
      {
        title: t('monitor.integrations.customApi.assetName'),
        dataIndex: 'instance_name',
        key: 'instance_name',
        width: 200,
        render: (value: string) => value || '--'
      },
      {
        title: t('monitor.integrations.customApi.instanceId'),
        dataIndex: 'instance_id',
        key: 'instance_id',
        width: 260,
        render: (_: string, record: PushAccessInstanceItem) => (
          <div className="flex items-center gap-2">
            <span className="min-w-0 font-mono text-[13px] text-[var(--color-text-1)]">
              {buildInstanceIdentityLabel(record, instanceIdKeys)}
            </span>
            <CopyOutlined
              className="cursor-pointer text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
              onClick={() =>
                copy(buildInstanceIdentityLabel(record, instanceIdKeys))
              }
            />
          </div>
        )
      },
      {
        title: t('monitor.integrations.customApi.belongOrganization'),
        dataIndex: 'organization',
        key: 'organization',
        width: 200,
        render: (_: any, record: PushAccessInstanceItem) =>
          renderOrganizationText(record)
      }
    ];

    return (
      <OperateModal
        open={visible}
        width={900}
        title={t('monitor.integrations.customApi.selectAccessAsset')}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              onClick={handleConfirm}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Space direction="vertical" size={16} className="w-full">
          <p className="mb-0 text-[var(--color-text-3)]">
            {t('monitor.integrations.customApi.selectAssetModalDesc')}
          </p>
          <Input
            allowClear
            placeholder={t(
              'monitor.integrations.customApi.searchAssetPlaceholder'
            )}
            value={assetKeyword}
            onChange={(e) => setAssetKeyword(e.target.value)}
          />
          <CustomTable
            rowKey="instance_id"
            loading={loading}
            dataSource={selectableAssets}
            columns={columns}
            rowSelection={{
              selectedRowKeys: draftSelectedInstanceIds,
              onChange: (keys) => setDraftSelectedInstanceIds(keys)
            }}
          />
        </Space>
      </OperateModal>
    );
  }
);

SelectAssetModal.displayName = 'SelectAssetModal';
export default SelectAssetModal;
