'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Form, Select, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { isValidCmdbInstanceUuid } from '@/app/ops-analysis/utils/cmdbInstanceUuid';

interface ModelOption {
  label: string;
  value: string;
}

export interface RelatedTopologyInstanceOption {
  label: string;
  value: string;
}

export function instanceOptionFromEntity(
  item: Record<string, unknown> | null | undefined,
): RelatedTopologyInstanceOption | null {
  if (!item || !isValidCmdbInstanceUuid(item.inst_uuid)) {
    return null;
  }
  return {
    value: String(item.inst_uuid),
    label: String(item.inst_name || item.name || item.inst_uuid),
  };
}

export function mergePinnedInstanceOption(
  options: RelatedTopologyInstanceOption[],
  pinned?: RelatedTopologyInstanceOption | null,
): RelatedTopologyInstanceOption[] {
  if (!pinned?.value) {
    return options;
  }
  if (options.some((item) => item.value === pinned.value)) {
    return options;
  }
  return [pinned, ...options];
}

export const RelatedTopologyAssetField = ({
  open,
  enabled,
}: {
  open: boolean;
  enabled: boolean;
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const { getModelList } = useModelApi();
  const { searchInstances, getInstanceDetail } = useInstanceApi();
  const getModelListRef = useRef(getModelList);
  const searchInstancesRef = useRef(searchInstances);
  const getInstanceDetailRef = useRef(getInstanceDetail);
  getModelListRef.current = getModelList;
  searchInstancesRef.current = searchInstances;
  getInstanceDetailRef.current = getInstanceDetail;
  const [models, setModels] = useState<ModelOption[]>([]);
  const [instances, setInstances] = useState<RelatedTopologyInstanceOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [instancesLoading, setInstancesLoading] = useState(false);
  const modelId = Form.useWatch(['relatedTopology', 'modelId'], form);
  const instUuid = Form.useWatch(['relatedTopology', 'instUuid'], form);

  useEffect(() => {
    if (!open || !enabled || models.length) return;
    let cancelled = false;
    setModelsLoading(true);
    getModelListRef.current()
      .then((list: Array<{ model_id?: string; model_name?: string }>) => {
        if (cancelled) return;
        setModels(
          (Array.isArray(list) ? list : [])
            .filter((item) => item?.model_id)
            .map((item) => ({
              value: String(item.model_id),
              label: String(item.model_name || item.model_id),
            })),
        );
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, models.length, open]);

  useEffect(() => {
    if (!open || !enabled || !modelId) {
      setInstances([]);
      return;
    }
    let cancelled = false;
    setInstancesLoading(true);
    const currentUuid = String(instUuid || '').trim();
    searchInstancesRef.current({
      model_id: modelId,
      query_list: [],
      page: 1,
      page_size: 50,
      order: '',
      role: '',
      case_sensitive: false,
    })
      .then(async (result: { insts?: Array<Record<string, unknown>> }) => {
        const listed = (result?.insts || []).flatMap((item) => {
          const option = instanceOptionFromEntity(item);
          return option ? [option] : [];
        });
        if (cancelled) return;
        if (
          currentUuid
          && isValidCmdbInstanceUuid(currentUuid)
          && !listed.some((item) => item.value === currentUuid)
        ) {
          try {
            const detail = await getInstanceDetailRef.current(currentUuid) as Record<string, unknown>;
            if (cancelled) return;
            const pinned = instanceOptionFromEntity(detail);
            if (pinned && String(detail?.model_id || '') === String(modelId)) {
              setInstances(mergePinnedInstanceOption(listed, pinned));
              return;
            }
          } catch {
            if (cancelled) return;
          }
        }
        setInstances(listed);
      })
      .finally(() => {
        if (!cancelled) setInstancesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, instUuid, modelId, open]);

  return (
    <>
      <Form.Item
        label={t('dashboard.relatedTopologyModel')}
        name={['relatedTopology', 'modelId']}
        rules={[
          { required: true, message: t('dashboard.relatedTopologyModelIdRequired') },
        ]}
      >
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          loading={modelsLoading}
          options={models}
          placeholder={t('common.selectTip')}
          onChange={() => {
            form.setFieldValue(['relatedTopology', 'instUuid'], undefined);
          }}
        />
      </Form.Item>
      <Form.Item
        label={t('dashboard.relatedTopologyAsset')}
        name={['relatedTopology', 'instUuid']}
        rules={[
          { required: true, message: t('dashboard.relatedTopologyInstUuidRequired') },
        ]}
      >
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          loading={instancesLoading}
          options={instances}
          placeholder={t('common.selectTip')}
          notFoundContent={instancesLoading ? <Spin size="small" /> : undefined}
        />
      </Form.Item>
    </>
  );
};
