'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Drawer,
  Form,
  Input,
  Radio,
  Select,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ModelItem } from '@/app/cmdb/types/assetManage';
import type { SceneViewRecord } from './groupScenes';
import type { SceneViewPayload } from '@/app/cmdb/api/sceneView';
import { useSceneViewApi } from '@/app/cmdb/api';

interface SceneEditorDrawerProps {
  open: boolean;
  scene: SceneViewRecord | null;
  modelList: ModelItem[];
  canOrgShare: boolean;
  canGlobal: boolean;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: SceneViewPayload) => Promise<void>;
}

const SceneEditorDrawer: React.FC<SceneEditorDrawerProps> = ({
  open,
  scene,
  modelList,
  canOrgShare,
  canGlobal,
  saving,
  onClose,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const { getSceneTagOptions } = useSceneViewApi();
  const [form] = Form.useForm();
  const modelIds = Form.useWatch('model_ids', form) as string[] | undefined;
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [tagLoading, setTagLoading] = useState(false);

  const modelOptions = useMemo(
    () =>
      (modelList || []).map((item) => ({
        value: item.model_id,
        label: item.model_name || item.model_id,
      })),
    [modelList]
  );

  const visibilityOptions = useMemo(() => {
    const options = [
      { value: 'personal', label: t('SceneView.visibilityPersonal') },
    ];
    if (canOrgShare) {
      options.push({ value: 'organization', label: t('SceneView.visibilityOrg') });
    }
    if (canGlobal) {
      options.push({ value: 'global', label: t('SceneView.visibilityGlobal') });
    }
    return options;
  }, [canGlobal, canOrgShare, t]);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      name: scene?.name || '',
      model_ids: scene?.model_ids || [],
      tags: scene?.tags || [],
      tag_match: scene?.tag_match || 'and',
      visibility: scene?.visibility || 'personal',
    });
  }, [form, open, scene]);

  useEffect(() => {
    if (!open) return;
    const ids = (modelIds || []).filter(Boolean);
    if (!ids.length) {
      setTagOptions([]);
      return;
    }
    let cancelled = false;
    setTagLoading(true);
    getSceneTagOptions(ids)
      .then((data) => {
        if (cancelled) return;
        const tags = data?.tags || [];
        setTagOptions(tags);
        const selected = (form.getFieldValue('tags') as string[]) || [];
        const next = selected.filter((item) => tags.includes(item));
        if (next.length !== selected.length) {
          form.setFieldValue('tags', next);
        }
      })
      .catch(() => {
        if (!cancelled) setTagOptions([]);
      })
      .finally(() => {
        if (!cancelled) setTagLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [form, getSceneTagOptions, modelIds, open]);

  return (
    <Drawer
      title={scene ? t('SceneView.edit') : t('SceneView.create')}
      open={open}
      onClose={onClose}
      destroyOnClose
      width={480}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            {t('common.confirm')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onSubmit({
            name: String(values.name || '').trim(),
            model_ids: values.model_ids,
            tags: values.tags,
            tag_match: values.tag_match,
            visibility: values.visibility,
          })
        }
      >
        <Form.Item
          name="name"
          label={t('SceneView.name')}
          rules={[{ required: true, message: t('SceneView.needName') }]}
        >
          <Input maxLength={128} />
        </Form.Item>
        <Form.Item
          name="model_ids"
          label={t('SceneView.models')}
          rules={[{ required: true, type: 'array', min: 1, message: t('SceneView.needModels') }]}
        >
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            options={modelOptions}
          />
        </Form.Item>
        <Form.Item
          name="tags"
          label={t('SceneView.tags')}
          rules={[{ required: true, type: 'array', min: 1, message: t('SceneView.needTags') }]}
        >
          <Select
            mode="multiple"
            showSearch
            loading={tagLoading}
            disabled={!modelIds?.length}
            placeholder={modelIds?.length ? undefined : t('SceneView.modelsFirst')}
            options={tagOptions.map((item) => ({ value: item, label: item }))}
          />
        </Form.Item>
        <Form.Item name="tag_match" label={t('SceneView.tagMatch')} initialValue="and">
          <Radio.Group>
            <Radio value="and">{t('SceneView.tagAnd')}</Radio>
            <Radio value="or">{t('SceneView.tagOr')}</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item name="visibility" label={t('SceneView.visibility')} initialValue="personal">
          <Radio.Group options={visibilityOptions} />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default SceneEditorDrawer;
