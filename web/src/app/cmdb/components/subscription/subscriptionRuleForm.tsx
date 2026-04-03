import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Form, Input, Radio, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { useCommon } from '@/app/cmdb/context/common';
import { useModelApi } from '@/app/cmdb/api';
import TriggerTypeConfig from './triggerTypeConfig';
import InstanceSelector from './instanceSelector';
import RecipientSelector from './recipientSelector';
import type {
  QuickSubscribeDefaults,
  SubscriptionRule,
  SubscriptionRuleCreate,
  TriggerConfig,
  TriggerType,
} from '@/app/cmdb/types/subscription';
import { useChannelApi } from '@/app/system-manager/api/channel';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

interface SubscriptionRuleFormProps {
  initialValues?: SubscriptionRule;
  quickDefaults?: QuickSubscribeDefaults;
  modelId: string;
  modelName: string;
  onSubmitAndEnable: (data: SubscriptionRuleCreate) => Promise<void>;
  onSubmitOnly: (data: SubscriptionRuleCreate) => Promise<void>;
}

export interface SubscriptionRuleFormRef {
  submit: (isEnabled: boolean) => Promise<void>;
}

const EMPTY_CONDITION_FILTER = { query_list: [] };
const EMPTY_INSTANCES_FILTER = { instance_ids: [] };

const SubscriptionRuleForm = forwardRef<SubscriptionRuleFormRef, SubscriptionRuleFormProps>(({ 
  initialValues,
  quickDefaults,
  modelId,
  modelName,
  onSubmitAndEnable,
  onSubmitOnly,
}, ref) => {
  const { t } = useTranslation();
  const { selectedGroup, userId } = useUserInfoContext();
  const common = useCommon();
  const { getModelAttrGroupsFullInfo, getModelAssociations } = useModelApi();
  const { getChannelData } = useChannelApi();
  const [form] = Form.useForm<SubscriptionRuleCreate>();
  const [triggerTypes, setTriggerTypes] = useState<TriggerType[]>(
    initialValues?.trigger_types || []
  );
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>(
    initialValues?.trigger_config || {}
  );
  const [channelOptions, setChannelOptions] = useState<{ label: string; value: number }[]>([]);
  const [modelFields, setModelFields] = useState<AttrFieldType[]>([]);
  const [relationFields, setRelationFields] = useState<AttrFieldType[]>([]);
  const [relatedModels, setRelatedModels] = useState<{ id: string; name: string }[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [triggerConfigErrors, setTriggerConfigErrors] = useState<Record<string, string>>({});
  const appliedInitKeyRef = useRef('');
  const watchedFilterType = Form.useWatch('filter_type', form);
  const watchedInstanceFilter = Form.useWatch('instance_filter', form);

  useEffect(() => {
    if (modelId) {
      getModelAttrGroupsFullInfo(modelId)
        .then((data: any) => {
          const groups = Array.isArray(data?.groups) ? data.groups : [];
          const fields = groups.flatMap((group: any) => (
            Array.isArray(group?.attrs) ? group.attrs : []
          ));
          setModelFields(fields);
        })
        .catch(() => {
          setModelFields([]);
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId]);

  useEffect(() => {
    if (!modelId) {
      setRelatedModels([]);
      return;
    }
    getModelAssociations(modelId)
      .then((data: any) => {
        const associations = Array.isArray(data) ? data : [];
        const nextModels = associations
          .map((item: any) => {
            const relatedModelId = item?.src_model_id === modelId ? item?.dst_model_id : item?.src_model_id;
            if (!relatedModelId || relatedModelId === modelId) {
              return null;
            }
            const model = common?.modelList?.find((entry) => entry.model_id === relatedModelId);
            return {
              id: relatedModelId,
              name: model?.model_name || relatedModelId,
            };
          })
          .filter(Boolean)
          .filter((item: any, index: number, list: any[]) => list.findIndex((entry) => entry.id === item.id) === index);
        setRelatedModels(nextModels);
      })
      .catch(() => {
        setRelatedModels([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, common?.modelList]);

  const RELATION_CHANGE_EXCLUDED_FIELD_IDS = useMemo(() => new Set([
    'inst_name',
    'organization',
    'collect_task',
    'update_time',
    'updated_time',
    'is_collect_task',
  ]), []);

  useEffect(() => {
    const relatedModelId = triggerConfig.relation_change?.related_model;
    if (!relatedModelId) {
      setRelationFields([]);
      return;
    }
    getModelAttrGroupsFullInfo(relatedModelId)
      .then((data: any) => {
        const groups = Array.isArray(data?.groups) ? data.groups : [];
        const fields = groups.flatMap((group: any) => (
          Array.isArray(group?.attrs) ? group.attrs : []
        ));
        setRelationFields(fields);
        const defaultFields = fields
          .filter((f: AttrFieldType) => !RELATION_CHANGE_EXCLUDED_FIELD_IDS.has(f.attr_id))
          .map((f: AttrFieldType) => f.attr_id);
        setTriggerConfig((prev) => ({
          ...prev,
          relation_change: {
            related_model: relatedModelId,
            fields: defaultFields,
          },
        }));
      })
      .catch(() => {
        setRelationFields([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerConfig.relation_change?.related_model]);

  const dateFields = useMemo(
    () => modelFields.filter((f) => ['time', 'date', 'datetime'].includes(f.attr_type)).map((f) => ({
      id: f.attr_id,
      name: f.attr_name,
    })),
    [modelFields]
  );

  useEffect(() => {
    getChannelData({ page: 1, page_size: 100 }).then((res: any) => {
      const list = Array.isArray(res)
        ? res
        : Array.isArray(res?.items)
          ? res.items
          : Array.isArray(res?.results)
            ? res.results
            : Array.isArray(res?.data)
              ? res.data
              : Array.isArray(res?.data?.results)
                ? res.data.results
                : Array.isArray(res?.data?.items)
                  ? res.data.items
                  : [];
      setChannelOptions(
        list
          .map((item: any) => ({
            label: item?.name || item?.display_name || '',
            value: Number(item?.id),
          }))
          .filter((item: { label: string; value: number }) => item.label && !Number.isNaN(item.value))
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const initialFormValues = useMemo<Partial<SubscriptionRuleCreate>>(() => {
    if (initialValues) {
      return { ...initialValues };
    }

    return {
      name: quickDefaults?.name || '',
      organization: quickDefaults?.organization || Number(selectedGroup?.id || 0),
      model_id: quickDefaults?.model_id || modelId,
      filter_type: quickDefaults?.filter_type || 'instances',
      instance_filter: quickDefaults?.instance_filter || { instance_ids: [] },
      trigger_types: [],
      trigger_config: {},
      recipients: quickDefaults?.recipients || {
        users: userId ? [Number(userId)] : [],
      },
      channel_ids: [],
      is_enabled: true,
    };
  }, [initialValues, quickDefaults, modelId, selectedGroup?.id, userId]);

  const initKey = useMemo(() => {
    if (initialValues?.id) {
      return `edit:${initialValues.id}`;
    }

    return `create:${quickDefaults?.source || 'drawer'}:${modelId}`;
  }, [initialValues?.id, quickDefaults?.source, modelId]);

  useEffect(() => {
    if (appliedInitKeyRef.current === initKey) {
      return;
    }

    form.setFieldsValue(initialFormValues as SubscriptionRuleCreate);
    appliedInitKeyRef.current = initKey;
  }, [form, initKey, initialFormValues]);

  const getPayload = useCallback(async (isEnabled: boolean): Promise<SubscriptionRuleCreate> => {
    const values = await form.validateFields();
    return {
      ...values,
      model_id: values.model_id || modelId,
      trigger_types: triggerTypes,
      trigger_config: triggerConfig,
      is_enabled: isEnabled,
    } as SubscriptionRuleCreate;
  }, [form, modelId, triggerTypes, triggerConfig]);

  const validateTriggerConfig = useCallback((): Record<string, string> => {
    const errors: Record<string, string> = {};
    const requiredMsg = t('common.selectMsg');
    
    if (triggerTypes.includes('attribute_change')) {
      const fields = triggerConfig.attribute_change?.fields || [];
      if (fields.length === 0) {
        errors['attribute_change.fields'] = requiredMsg;
      }
    }
    
    if (triggerTypes.includes('relation_change')) {
      const relatedModel = triggerConfig.relation_change?.related_model;
      const fields = triggerConfig.relation_change?.fields || [];
      if (!relatedModel) {
        errors['relation_change.related_model'] = requiredMsg;
      }
      if (fields.length === 0) {
        errors['relation_change.fields'] = requiredMsg;
      }
    }
    
    if (triggerTypes.includes('expiration')) {
      const timeField = triggerConfig.expiration?.time_field;
      if (!timeField) {
        errors['expiration.time_field'] = requiredMsg;
      }
    }
    
    return errors;
  }, [triggerTypes, triggerConfig, t]);

  const handleSubmit = useCallback(async (isEnabled: boolean) => {
    setSubmitted(true);
    
    const configErrors = validateTriggerConfig();
    setTriggerConfigErrors(configErrors);
    
    if (triggerTypes.length === 0 || Object.keys(configErrors).length > 0) {
      return;
    }
    try {
      const payload = await getPayload(isEnabled);
      if (isEnabled) {
        await onSubmitAndEnable(payload);
        return;
      }
      await onSubmitOnly(payload);
    } catch (error: any) {
      if (Array.isArray(error?.errorFields)) {
        return;
      }
      throw error;
    }
  }, [getPayload, onSubmitAndEnable, onSubmitOnly, triggerTypes.length, validateTriggerConfig]);

  useImperativeHandle(ref, () => ({
    submit: handleSubmit,
  }), [handleSubmit]);

  const currentFilterType = watchedFilterType || quickDefaults?.filter_type || initialValues?.filter_type || 'instances';
  const currentInstanceFilter = useMemo(() => {
    if (watchedInstanceFilter) return watchedInstanceFilter;
    if (initialValues?.instance_filter) return initialValues.instance_filter;
    if (quickDefaults?.instance_filter) return quickDefaults.instance_filter;
    return currentFilterType === 'condition' ? EMPTY_CONDITION_FILTER : EMPTY_INSTANCES_FILTER;
  }, [watchedInstanceFilter, initialValues?.instance_filter, quickDefaults?.instance_filter, currentFilterType]);

  const handleInstanceFilterChange = useCallback(
    (v: any) => form.setFieldValue('instance_filter', v),
    [form]
  );

  const handleRecipientsChange = useCallback(
    (v: any) => form.setFieldValue('recipients', v),
    [form]
  );

  const horizontalLayout = {
    labelCol: { flex: '80px' },
    wrapperCol: { flex: 1 },
  };

  return (
    <Form form={form} layout="vertical">
      <Form.Item
        label={t('subscription.ruleName')}
        name="name"
        rules={[{ required: true, message: t('subscription.ruleName') }]}
        {...horizontalLayout}
        layout="horizontal"
      >
        <Input maxLength={128} />
      </Form.Item>

      <Form.Item 
        label={t('subscription.organization')} 
        name="organization" 
        rules={[{ required: true }]}
        {...horizontalLayout}
        layout="horizontal"
      > 
        <Select
          disabled
          options={selectedGroup ? [{ label: selectedGroup.name, value: Number(selectedGroup.id) }] : []}
        />
      </Form.Item>

      <Form.Item 
        label={t('subscription.targetModel')} 
        name="model_id" 
        rules={[{ required: true }]}
        {...horizontalLayout}
        layout="horizontal"
      > 
        <Select disabled options={[{ label: modelName, value: modelId }]} />
      </Form.Item>

      <Form.Item 
        label={t('subscription.filterType')} 
        required
        style={{ marginBottom: 32 }}
      >
        <div style={{ marginLeft: 80, marginTop: -30 }}>
          <Form.Item name="filter_type" rules={[{ required: true }]} style={{ marginBottom: 8 }}> 
            <Radio.Group
              options={[
                { label: t('subscription.filterTypeInstances'), value: 'instances' },
                { label: t('subscription.filterTypeCondition'), value: 'condition' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="instance_filter"
            style={{ marginBottom: 0 }}
            validateTrigger={[]}
            rules={[
              {
                validator: async (_, value) => {
                  if (currentFilterType === 'instances') {
                    if (Array.isArray(value?.instance_ids) && value.instance_ids.length > 0) {
                      return;
                    }
                    throw new Error(t('subscription.selectInstances'));
                  }

                  if (Array.isArray(value?.query_list) && value.query_list.length > 0) {
                    return;
                  }
                  throw new Error(t('subscription.filterTypeCondition'));
                },
              },
            ]}
          >
            <InstanceSelector
              filterType={currentFilterType}
              value={currentInstanceFilter}
              onChange={handleInstanceFilterChange}
              modelId={modelId}
              modelFields={modelFields}
            />
          </Form.Item>
        </div>
      </Form.Item>

      <Form.Item
        label={t('subscription.triggerType')}
        required
        validateStatus={submitted && triggerTypes.length === 0 ? 'error' : ''}
        help={submitted && triggerTypes.length === 0 ? t('subscription.atLeastOneTriggerType') : ''}
        style={{ marginBottom: 32 }}
      >
        <div style={{ marginLeft: 80, marginTop: -30 }}>
          <TriggerTypeConfig
            value={triggerTypes}
            onChange={(types, config) => {
              setTriggerTypes(types);
              setTriggerConfig(config);
              if (submitted) {
                setTriggerConfigErrors({});
              }
            }}
            modelFields={modelFields.map((field) => ({ id: field.attr_id, name: field.attr_name, type: field.attr_type }))}
            relatedModels={relatedModels}
            relationFields={relationFields.map((field) => ({ id: field.attr_id, name: field.attr_name, type: field.attr_type }))}
            dateFields={dateFields}
            triggerConfig={triggerConfig}
            errors={triggerConfigErrors}
          />
        </div>
      </Form.Item>

      <Form.Item
        label={t('subscription.recipients')}
        name="recipients"
        rules={[{ required: true }]}
        {...horizontalLayout}
        layout="horizontal"
      >
        <RecipientSelector
          value={form.getFieldValue('recipients') || { users: [] }}
          onChange={handleRecipientsChange}
        />
      </Form.Item>

      <Form.Item
        label={t('subscription.notificationChannel')}
        name="channel_ids"
        rules={[{ required: true, message: t('subscription.notificationChannel') }]}
        {...horizontalLayout}
        layout="horizontal"
      >
        <Select mode="multiple" options={channelOptions} maxTagCount="responsive" maxTagTextLength={12} />
      </Form.Item>

    </Form>
  );
});

export default SubscriptionRuleForm;
