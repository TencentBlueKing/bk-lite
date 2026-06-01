'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Modal, Space, Switch, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useModelDetail } from '../context';
import type {
  AutoAssociationRuleAssociationItem,
  AutoAssociationRuleFormAssociationItem,
  AttrFieldType,
  ModelAutoAssociationRuleItem,
  ModelAutoAssociationRuleListResponse,
} from '@/app/cmdb/types/assetManage';
import AutoAssociationRuleModal, { AutoAssociationRuleModalRef } from './autoAssociationRuleModal';
import { CONSTRAINT_List } from '@/app/cmdb/constants/asset';

const AutoAssociationRulesPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { confirm } = Modal;
  const modalRef = useRef<AutoAssociationRuleModalRef>(null);
  const commonContext = useCommon();
  const modelDetail = useModelDetail();
  const modelId = modelDetail?.model_id;
  const modelPermission = modelDetail?.permission || [];
  const modelList = commonContext?.modelList || [];
  const {
    getModelAttrList,
    getModelAssociations,
    getModelAutoAssociationRules,
    createModelAutoAssociationRule,
    updateModelAutoAssociationRule,
    deleteModelAutoAssociationRule,
  } = useModelApi();

  const [loading, setLoading] = useState(false);
  const [submittingRuleId, setSubmittingRuleId] = useState<string>('');
  const [rules, setRules] = useState<ModelAutoAssociationRuleItem[]>([]);
  const [editableAssociations, setEditableAssociations] = useState<AutoAssociationRuleFormAssociationItem[]>([]);
  const [currentModelAttrs, setCurrentModelAttrs] = useState<AttrFieldType[]>([]);
  const [allModelAttrsMap, setAllModelAttrsMap] = useState<Record<string, AttrFieldType[]>>({});

  const modelNameMap = useMemo(
    () => Object.fromEntries(modelList.map((item) => [item.model_id, item.model_name])),
    [modelList],
  );

  const mapAssociationToFormContext = (item: AutoAssociationRuleAssociationItem): AutoAssociationRuleFormAssociationItem => {
    const currentSide = item.src_model_id === modelId ? 'src' : 'dst';
    const formSourceModelId = modelId || item.src_model_id;
    const formTargetModelId = currentSide === 'src' ? item.dst_model_id : item.src_model_id;
    return {
      ...item,
      current_side: currentSide,
      form_source_model_id: formSourceModelId,
      form_source_model_name: modelDetail?.model_name || modelNameMap[formSourceModelId] || formSourceModelId,
      form_target_model_id: formTargetModelId,
      form_target_model_name: modelNameMap[formTargetModelId] || formTargetModelId,
    };
  };

  const loadData = async () => {
    if (!modelId) return;
    setLoading(true);
    try {
      const [ruleData, attrData, associationData] = await Promise.all([
        getModelAutoAssociationRules(modelId) as Promise<ModelAutoAssociationRuleListResponse>,
        getModelAttrList(modelId) as Promise<AttrFieldType[]>,
        getModelAssociations(modelId) as Promise<AutoAssociationRuleAssociationItem[]>,
      ]);
      setRules(ruleData || []);
      setCurrentModelAttrs(attrData || []);
      const formAssociations = (associationData || []).map(mapAssociationToFormContext);
      setEditableAssociations(formAssociations);

      const targetModelIds = Array.from(
        new Set(
          formAssociations
            .map((item) => String(item.form_target_model_id || ''))
            .filter(Boolean),
        ),
      );
      const targetAttrEntries = await Promise.all(
        targetModelIds.map(async (targetModelId) => {
          const attrs = await getModelAttrList(targetModelId) as AttrFieldType[];
          return [targetModelId, attrs || []] as const;
        }),
      );
      setAllModelAttrsMap(Object.fromEntries(targetAttrEntries));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [modelDetail?.model_name, modelId, modelNameMap]);

  const unsupportedAttrTypes = useMemo(() => new Set(['enum', 'tag', 'table', 'organization', 'user']), []);

  const creatableRules = useMemo(() => {
    return editableAssociations.filter((item) => {
      const validCurrentAttrs = currentModelAttrs.filter((field) => {
        const attrType = String(field.attr_type || '');
        return attrType && !unsupportedAttrTypes.has(attrType);
      });
      const targetAttrs = allModelAttrsMap[item.form_target_model_id] || [];
      const validTargetTypes = new Set(
        targetAttrs
          .map((field) => String(field.attr_type || ''))
          .filter((attrType) => attrType && !unsupportedAttrTypes.has(attrType)),
      );
      return validCurrentAttrs.some((field) => validTargetTypes.has(String(field.attr_type || '')));
    });
  }, [allModelAttrsMap, currentModelAttrs, editableAssociations, unsupportedAttrTypes]);

  const showModal = (mode: 'create' | 'edit', rule?: ModelAutoAssociationRuleItem) => {
    modalRef.current?.showModal({
      mode,
      rule,
      associations: mode === 'create' ? creatableRules : editableAssociations,
      currentModelAttrs,
      allModelAttrsMap,
    });
  };

  const handleDelete = (record: ModelAutoAssociationRuleItem) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteModelAutoAssociationRule(modelId!, record.model_asst_id, record.rule_id);
        message.success(t('successfullyDeleted'));
        await loadData();
      },
    });
  };

  const handleToggle = async (record: ModelAutoAssociationRuleItem, enabled: boolean) => {
    const currentRule = record.auto_relation_rule;
    setSubmittingRuleId(`${record.model_asst_id}-${record.rule_id}`);
    try {
      await updateModelAutoAssociationRule(modelId!, record.model_asst_id, record.rule_id, {
        enabled,
        match_pairs: currentRule.match_pairs,
      });
      message.success(t(enabled ? 'Model.enableAutoAssociationRuleSuccess' : 'Model.disableAutoAssociationRuleSuccess'));
      await loadData();
    } finally {
      setSubmittingRuleId('');
    }
  };

  const getCurrentSide = (record: ModelAutoAssociationRuleItem) => {
    return record.src_model_id === modelId ? 'src' : 'dst';
  };

  const getModelName = (modelKey: string) => {
    if (modelKey === modelId && modelDetail?.model_name) {
      return modelDetail.model_name;
    }
    return modelNameMap[modelKey] || modelKey || '--';
  };

  const getRelationName = (record: ModelAutoAssociationRuleItem) => {
    if (typeof record.asst_name === 'string' && record.asst_name) {
      return record.asst_name;
    }
    return record.asst_id || '--';
  };

  const getAssociationName = (record: ModelAutoAssociationRuleItem) => {
    return `${getModelName(record.src_model_id)}_${getRelationName(record)}_${getModelName(record.dst_model_id)}`;
  };

  const columns: ColumnsType<ModelAutoAssociationRuleItem> = [
    {
      title: t('name', 'Name'),
      dataIndex: 'model_asst_id',
      key: 'model_asst_id',
      render: (_, record) => getAssociationName(record),
    },
    {
      title: t('Model.sourceModel', 'Source Model'),
      key: 'src_model_id',
      render: (_, record) => getModelName(record.src_model_id),
    },
    {
      title: t('Model.targetModel', 'Target Model'),
      key: 'target_model_id',
      render: (_, record) => getModelName(record.dst_model_id),
    },
    {
      title: t('Model.constraint', 'Constraint'),
      dataIndex: 'mapping',
      key: 'mapping',
      render: (_, record) => CONSTRAINT_List.find((item) => item.id === record.mapping)?.name || record.mapping || '--',
    },
    {
      title: t('Model.matchPairs', 'Match Pairs'),
      key: 'match_pairs',
      render: (_, record) => {
        const pairs = record.auto_relation_rule?.match_pairs || [];
        return pairs.length ? (
            <Space wrap>
              {pairs.map((pair) => (
                <Tag key={`${record.model_asst_id}-${record.rule_id}-${pair.src_field_id}-${pair.dst_field_id}`}>
                  {getCurrentSide(record) === 'src'
                    ? `${pair.src_field_id} = ${pair.dst_field_id}`
                    : `${pair.dst_field_id} = ${pair.src_field_id}`}
                </Tag>
              ))}
          </Space>
        ) : '--';
      },
    },
    {
      title: t('Model.ruleStatus', 'Rule Status'),
      key: 'enabled',
      render: (_, record) => {
        const enabled = Boolean(record.auto_relation_rule?.enabled);
        return (
          <Switch
            checked={enabled}
            loading={submittingRuleId === `${record.model_asst_id}-${record.rule_id}`}
            checkedChildren={t('Model.enabled', 'Enabled')}
            unCheckedChildren={t('Model.disabled', 'Disabled')}
            onChange={(checked) => handleToggle(record, checked)}
          />
        );
      },
    },
    {
      title: t('Model.updatedBy', 'Updated By'),
      key: 'updated_by',
      render: (_, record) => record.auto_relation_rule?.updated_by || '--',
    },
    {
      title: t('Model.updatedAt', 'Updated At'),
      key: 'updated_at',
      render: (_, record) => {
        const updatedAt = record.auto_relation_rule?.updated_at;
        return updatedAt ? convertToLocalizedTime(updatedAt) : '--';
      },
    },
    {
      title: t('common.action', 'Actions'),
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              onClick={() => showModal('edit', record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              danger
              onClick={() => handleDelete(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Alert className="mb-[12px]" type="info" showIcon banner message={t('Model.autoAssociationRuleTip')} />
      <div className="flex justify-end mb-[16px]">
        <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
          <Button type="primary" disabled={!creatableRules.length} onClick={() => showModal('create')}>
            {t('Model.addAutoAssociationRule')}
          </Button>
        </PermissionWrapper>
      </div>
      <CustomTable
        size="middle"
        columns={columns}
        dataSource={rules}
        loading={loading}
        rowKey={(record) => `${record.model_asst_id}-${record.rule_id}`}
        pagination={false}
        scroll={{ y: 'calc(100vh - 450px)' }}
      />
      <AutoAssociationRuleModal
        ref={modalRef}
        onSubmit={async (payload, editingRule) => {
          if (!modelId) return;
          if (editingRule) {
            await updateModelAutoAssociationRule(modelId, editingRule.model_asst_id, editingRule.rule_id, {
              enabled: payload.enabled,
              match_pairs: payload.match_pairs,
            });
            message.success(t('successfullyModified'));
          } else {
            await createModelAutoAssociationRule(modelId, {
              model_asst_id: String(payload.model_asst_id || ''),
              enabled: payload.enabled,
              match_pairs: payload.match_pairs,
            });
            message.success(t('successfullyAdded'));
          }
          await loadData();
        }}
      />
    </div>
  );
};

export default AutoAssociationRulesPage;
