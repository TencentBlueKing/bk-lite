'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Button, Form, Modal, Select, Space, Switch, Tag, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type {
  AttrFieldType,
  AutoAssociationRuleFormAssociationItem,
  AutoAssociationRulePayload,
  ModelAutoAssociationRuleItem,
} from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';

const LONG_TOOLTIP_OVERLAY_STYLE = {
  maxWidth: 'min(520px, calc(100vw - 48px))',
};

interface AutoAssociationRuleModalConfig {
  mode: 'create' | 'edit';
  associations: AutoAssociationRuleFormAssociationItem[];
  currentModelAttrs: AttrFieldType[];
  allModelAttrsMap: Record<string, AttrFieldType[]>;
  rule?: ModelAutoAssociationRuleItem;
}

export interface AutoAssociationRuleModalRef {
  showModal: (config: AutoAssociationRuleModalConfig) => void;
}

interface Props {
  onSubmit: (
    payload: AutoAssociationRulePayload,
    editingRule?: Pick<ModelAutoAssociationRuleItem, 'model_asst_id' | 'rule_id'>,
  ) => Promise<void>;
}

interface FormValues {
  model_asst_id?: string;
  enabled: boolean;
  source_field_ids: string[];
  target_field_ids: string[];
}

interface MatchPairFormItem {
  src_field_id?: string;
  dst_field_id?: string;
}

const AutoAssociationRuleModal = forwardRef<AutoAssociationRuleModalRef, Props>(({ onSubmit }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const [visible, setVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [rule, setRule] = useState<ModelAutoAssociationRuleItem | undefined>();
  const [associations, setAssociations] = useState<AutoAssociationRuleFormAssociationItem[]>([]);
  const [currentModelAttrs, setCurrentModelAttrs] = useState<AttrFieldType[]>([]);
  const [allModelAttrsMap, setAllModelAttrsMap] = useState<Record<string, AttrFieldType[]>>({});
  const previousAssociationIdRef = useRef<string | undefined>(undefined);

  useImperativeHandle(ref, () => ({
    showModal: (config) => {
      setMode(config.mode);
      setRule(config.rule);
      setAssociations(config.associations);
      setCurrentModelAttrs(config.currentModelAttrs);
      setAllModelAttrsMap(config.allModelAttrsMap);
      setVisible(true);

      const initialModelAsstId = config.rule?.model_asst_id || config.associations[0]?.model_asst_id;
      const initialRule = config.rule?.auto_relation_rule;
      const initialAssociation = config.associations.find((item) => item.model_asst_id === initialModelAsstId);
      previousAssociationIdRef.current = initialModelAsstId;
      form.setFieldsValue({
        model_asst_id: initialModelAsstId,
        enabled: initialRule?.enabled ?? true,
        source_field_ids: initialRule?.match_pairs?.length
          ? initialRule.match_pairs.map((pair) => (
            initialAssociation?.current_side === 'dst' ? pair.dst_field_id : pair.src_field_id
          ))
          : [],
        target_field_ids: initialRule?.match_pairs?.length
          ? initialRule.match_pairs.map((pair) => (
            initialAssociation?.current_side === 'dst' ? pair.src_field_id : pair.dst_field_id
          ))
          : [],
      });
    },
  }));

  useEffect(() => {
    if (!visible) {
      previousAssociationIdRef.current = undefined;
      form.resetFields();
    }
  }, [visible, form]);

  const unsupportedAttrTypes = useMemo(() => new Set(['enum', 'tag', 'table', 'organization', 'user']), []);

  const selectedModelAsstId = Form.useWatch('model_asst_id', form);
  const selectedSourceFieldIds = (Form.useWatch('source_field_ids', form) || []) as string[];
  const selectedTargetFieldIds = (Form.useWatch('target_field_ids', form) || []) as string[];

  const selectedAssociation = useMemo(
    () => associations.find((item) => item.model_asst_id === selectedModelAsstId),
    [associations, selectedModelAsstId],
  );

  const associationOptions = useMemo(() => {
    return associations.map((item) => ({
      label: `${item.model_asst_id} (${item.form_target_model_id})`,
      value: item.model_asst_id,
    }));
  }, [associations]);

  const selectedTargetAttrs = useMemo(() => {
    const targetModelId = selectedAssociation?.form_target_model_id;
    return targetModelId ? (allModelAttrsMap[targetModelId] || []) : [];
  }, [allModelAttrsMap, selectedAssociation]);

  const currentModelFieldsLabel = selectedAssociation?.form_source_model_id
    ? `${t('Model.currentModelFields', 'Current Model Fields')} (${selectedAssociation.form_source_model_name || selectedAssociation.form_source_model_id})`
    : t('Model.currentModelFields', 'Current Model Fields');

  const relatedModelFieldsLabel = selectedAssociation?.form_target_model_id
    ? `${t('Model.relatedModelFields', 'Related Model Fields')} (${selectedAssociation.form_target_model_name || selectedAssociation.form_target_model_id})`
    : t('Model.relatedModelFields', 'Related Model Fields');

  const currentFieldTypeMap = useMemo(
    () => new Map(currentModelAttrs.map((field) => [field.attr_id, String(field.attr_type || '')])),
    [currentModelAttrs],
  );

  const targetFieldTypeMap = useMemo(
    () => new Map(selectedTargetAttrs.map((field) => [field.attr_id, String(field.attr_type || '')])),
    [selectedTargetAttrs],
  );

  const currentFieldLabelMap = useMemo(
    () => new Map(currentModelAttrs.map((field) => [field.attr_id, `${field.attr_name} (${field.attr_id})`])),
    [currentModelAttrs],
  );

  const targetFieldLabelMap = useMemo(
    () => new Map(selectedTargetAttrs.map((field) => [field.attr_id, `${field.attr_name} (${field.attr_id})`])),
    [selectedTargetAttrs],
  );

  const selectableTargetTypes = useMemo(() => {
    return new Set(
      selectedTargetAttrs
        .map((field) => String(field.attr_type || ''))
        .filter((attrType) => attrType && !unsupportedAttrTypes.has(attrType)),
    );
  }, [selectedTargetAttrs, unsupportedAttrTypes]);

  const srcFieldOptions = useMemo(() => {
    return currentModelAttrs
      .filter((field) => {
        const attrType = String(field.attr_type || '');
        return attrType && !unsupportedAttrTypes.has(attrType) && selectableTargetTypes.has(attrType);
      })
      .map((field) => ({
        label: `${field.attr_name} (${field.attr_id})`,
        value: field.attr_id,
      }));
  }, [currentModelAttrs, selectableTargetTypes, unsupportedAttrTypes]);

  const targetFieldOptions = useMemo(() => {
    const allowedTypes = new Set<string>();

    selectedSourceFieldIds.forEach((fieldId) => {
      const attrType = currentFieldTypeMap.get(fieldId);
      if (attrType) {
        allowedTypes.add(attrType);
      }
    });

    const filterByType = allowedTypes.size > 0 ? allowedTypes : selectableTargetTypes;
    return selectedTargetAttrs
      .filter((field) => {
        const attrType = String(field.attr_type || '');
        return attrType && !unsupportedAttrTypes.has(attrType);
      })
      .filter((field) => filterByType.has(String(field.attr_type || '')))
      .map((field) => ({
        label: `${field.attr_name} (${field.attr_id})`,
        value: field.attr_id,
      }));
  }, [currentFieldTypeMap, selectableTargetTypes, selectedSourceFieldIds, selectedTargetAttrs, unsupportedAttrTypes]);

  useEffect(() => {
    if (!visible || !selectedModelAsstId) {
      return;
    }

    if (previousAssociationIdRef.current && previousAssociationIdRef.current !== selectedModelAsstId) {
      form.setFieldsValue({
        source_field_ids: [],
        target_field_ids: [],
      });
    }

    previousAssociationIdRef.current = selectedModelAsstId;
  }, [form, selectedModelAsstId, visible]);

  const getMatchPairState = (sourceFieldIds: string[] = [], targetFieldIds: string[] = []) => {
    const sourceByType = sourceFieldIds.reduce<Record<string, string[]>>((acc, fieldId) => {
      const attrType = currentFieldTypeMap.get(fieldId);
      if (!attrType) {
        return acc;
      }
      if (!acc[attrType]) {
        acc[attrType] = [];
      }
      acc[attrType].push(fieldId);
      return acc;
    }, {});

    const targetByType = targetFieldIds.reduce<Record<string, string[]>>((acc, fieldId) => {
      const attrType = targetFieldTypeMap.get(fieldId);
      if (!attrType) {
        return acc;
      }
      if (!acc[attrType]) {
        acc[attrType] = [];
      }
      acc[attrType].push(fieldId);
      return acc;
    }, {});

    const allTypes = Array.from(new Set([...Object.keys(sourceByType), ...Object.keys(targetByType)]));
    const hasTypeCountMismatch = allTypes.some(
      (attrType) => (sourceByType[attrType]?.length || 0) !== (targetByType[attrType]?.length || 0),
    );

    if (hasTypeCountMismatch) {
      return {
        hasTypeCountMismatch,
        pairs: [] as MatchPairFormItem[],
      };
    }

    const targetQueues = Object.fromEntries(
      Object.entries(targetByType).map(([attrType, fieldIds]) => [attrType, [...fieldIds]]),
    ) as Record<string, string[]>;

    const pairs = sourceFieldIds.reduce<MatchPairFormItem[]>((acc, sourceFieldId) => {
      const attrType = currentFieldTypeMap.get(sourceFieldId);
      const targetFieldId = attrType ? targetQueues[attrType]?.shift() : undefined;
      if (!sourceFieldId || !targetFieldId) {
        return acc;
      }
      acc.push({
        src_field_id: sourceFieldId,
        dst_field_id: targetFieldId,
      });
      return acc;
    }, []);

    return {
      hasTypeCountMismatch: false,
      pairs,
    };
  };

  const matchPairState = useMemo(
    () => getMatchPairState(selectedSourceFieldIds, selectedTargetFieldIds),
    [selectedSourceFieldIds, selectedTargetFieldIds, currentFieldTypeMap, targetFieldTypeMap],
  );

  const handleOk = async () => {
    const values = await form.validateFields();
    const nextMatchPairState = getMatchPairState(values.source_field_ids || [], values.target_field_ids || []);
    setSubmitting(true);
    try {
      await onSubmit(
        {
          model_asst_id: values.model_asst_id,
          enabled: Boolean(values.enabled),
          match_pairs: nextMatchPairState.pairs.map((item) => {
            const currentFieldId = String(item.src_field_id || '');
            const relatedFieldId = String(item.dst_field_id || '');
            if (selectedAssociation?.current_side === 'dst') {
              return {
                src_field_id: relatedFieldId,
                dst_field_id: currentFieldId,
              };
            }
            return {
              src_field_id: currentFieldId,
              dst_field_id: relatedFieldId,
            };
          }),
        },
        rule
          ? {
            model_asst_id: rule.model_asst_id,
            rule_id: rule.rule_id,
          }
          : undefined,
      );
      setVisible(false);
      form.resetFields();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={visible}
      width={720}
      title={mode === 'create' ? t('Model.addAutoAssociationRule') : t('Model.editAutoAssociationRule')}
      onCancel={() => setVisible(false)}
      maskClosable={false}
      centered
      footer={[
        <Button key="cancel" onClick={() => setVisible(false)}>
          {t('common.cancel')}
        </Button>,
        <Button key="ok" type="primary" loading={submitting} onClick={handleOk}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Form<FormValues> form={form} layout="vertical" className="mt-4">
        <Form.Item
          label={t('Model.targetModelAssociation')}
          name="model_asst_id"
          rules={[{ required: true, message: t('required') }]}
        >
          <Select
            options={associationOptions}
            disabled={mode === 'edit'}
            placeholder={t('common.selectMsg')}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

        <Form.Item label={t('Model.ruleStatus')} name="enabled" valuePropName="checked">
          <Switch checkedChildren={t('Model.enabled')} unCheckedChildren={t('Model.disabled')} />
        </Form.Item>

        <div className="rounded border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-4">
          <div className="mb-3">
            <div className="flex items-center gap-1 font-medium text-[var(--color-text-1)]">
              <span>{t('Model.matchPairs')}</span>
              <Tooltip
                overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                title={t('Model.matchPairSelectionTip', 'Select source and target fields in bulk. Fields are paired by matching type and selection order.')}
              >
                <QuestionCircleOutlined className="text-[var(--color-text-tertiary)]" />
              </Tooltip>
            </div>
          </div>

          <Space direction="vertical" className="w-full" size={12}>
            <Form.Item
              label={currentModelFieldsLabel}
              name="source_field_ids"
              rules={[
                { required: true, type: 'array', min: 1, message: t('required') },
                {
                  validator: async (_, value) => {
                    const sourceFieldIds = (value || []) as string[];
                    const targetFieldIds = (form.getFieldValue('target_field_ids') || []) as string[];
                    if (!sourceFieldIds.length || !targetFieldIds.length) {
                      return;
                    }
                    if (getMatchPairState(sourceFieldIds, targetFieldIds).hasTypeCountMismatch) {
                      throw new Error(t('Model.matchPairCountMismatch', 'For each selected field type, source and target counts must match.'));
                    }
                  },
                },
              ]}
              className="mb-0"
            >
              <Select
                mode="multiple"
                options={srcFieldOptions}
                placeholder={t('common.selectMsg')}
                showSearch
                optionFilterProp="label"
                maxTagCount="responsive"
              />
            </Form.Item>

            <Form.Item
              label={relatedModelFieldsLabel}
              name="target_field_ids"
              rules={[
                { required: true, type: 'array', min: 1, message: t('required') },
                {
                  validator: async (_, value) => {
                    const targetFieldIds = (value || []) as string[];
                    const sourceFieldIds = (form.getFieldValue('source_field_ids') || []) as string[];
                    if (!sourceFieldIds.length || !targetFieldIds.length) {
                      return;
                    }
                    if (getMatchPairState(sourceFieldIds, targetFieldIds).hasTypeCountMismatch) {
                      throw new Error(t('Model.matchPairCountMismatch', 'For each selected field type, source and target counts must match.'));
                    }
                  },
                },
              ]}
              className="mb-0"
            >
              <Select
                mode="multiple"
                options={targetFieldOptions}
                placeholder={t('common.selectMsg')}
                showSearch
                optionFilterProp="label"
                maxTagCount="responsive"
              />
            </Form.Item>

            <div>
              <div className="mb-2 font-medium text-[var(--color-text-1)]">{t('Model.matchPairPreview', 'Pair Preview')}</div>
              <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-3">
                {matchPairState.hasTypeCountMismatch ? (
                  <span className="text-sm text-[var(--color-text-3)]">{t('Model.matchPairCountMismatch', 'For each selected field type, source and target counts must match.')}</span>
                ) : matchPairState.pairs.length ? (
                  <Space wrap size={[8, 8]}>
                    {matchPairState.pairs.map((pair) => (
                      <Tag key={`${pair.src_field_id}-${pair.dst_field_id}`}>
                        {`${currentFieldLabelMap.get(String(pair.src_field_id || '')) || '--'} = ${targetFieldLabelMap.get(String(pair.dst_field_id || '')) || '--'}`}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <span className="text-sm text-[var(--color-text-3)]">{t('Model.matchPairPreviewEmpty', 'Select fields to preview generated match pairs.')}</span>
                )}
              </div>
            </div>
          </Space>
        </div>
      </Form>
    </Modal>
  );
});

AutoAssociationRuleModal.displayName = 'AutoAssociationRuleModal';

export default AutoAssociationRuleModal;
