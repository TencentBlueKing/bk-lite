import React, { useState, useEffect } from 'react';
import informationList from './list.module.scss';
import { Form, Button, Collapse, Descriptions, message, Select, Tooltip } from 'antd';
import {
  deepClone,
  getFieldItem,
  getValidationRules,
  normalizeTimeValueForForm,
  normalizeTimeValueForSubmit,
} from '@/app/cmdb/utils/common';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { DescriptionsProps } from 'antd';
import PermissionWrapper from '@/components/permission';
import {
  AssetDataFieldProps,
  AttrFieldType,
} from '@/app/cmdb/types/assetManage';
import {
  EditOutlined,
  BellOutlined,
  CopyOutlined,
  CheckOutlined,
  CloseOutlined,
  CaretRightOutlined,
  DownOutlined,
  UpOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useInstanceApi } from '@/app/cmdb/api';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import { useUserInfoContext } from '@/context/userInfo';
import { useClientData } from '@/context/client';
import TagCapsuleGroup from '@/components/tag-capsule-group';
import {
  canSyncMonitor,
  showNodeId,
  isMonitorSold,
  resolveMonitorLinkMessage,
} from '@/app/cmdb/utils/systemLinkage';

const { Panel } = Collapse;
const InfoList: React.FC<AssetDataFieldProps> = ({
  propertyList,
  userList,
  instDetail,
  onsuccessEdit,
  onSubscribe,
}) => {
  const [form] = Form.useForm();
  const [fieldList, setFieldList] = useState<DescriptionsProps['items']>([]);
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [isBatchEdit, setIsBatchEdit] = useState<boolean>(false);
  const [isBatchSaving, setIsBatchSaving] = useState<boolean>(false);
  const [editScenario, setEditScenario] = useState<string>('ordinary_attribute_change');
  const [collapsedTableFields, setCollapsedTableFields] = useState<Record<string, boolean>>({});
  const [isSyncingMonitor, setIsSyncingMonitor] = useState(false);
  const { t } = useTranslation();
  const { flatGroups } = useUserInfoContext();
  const { clientData } = useClientData();

  const { updateInstance, getInstanceProxys, pushToMonitor } = useInstanceApi();

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instUuid: string = searchParams.get('inst_uuid') || '';

  const cloudOptions = (useAssetDataStore.getState().cloud_list || []).map((item: any) => ({
    proxy_id: String(item.proxy_id),
    proxy_name: item.proxy_name,
  }));

  useEffect(() => {
    if (['host', 'subnet'].includes(modelId)) {
      getInstanceProxys()
        .then((data: any[]) => {
          useAssetDataStore.getState().setCloudList(data || []);
        })
        .catch(() => {
          console.error('Failed to fetch cloud list');
        });
    }
  }, []);

  useEffect(() => {
    const list = deepClone(propertyList)
      .map((group: any) => ({
        ...group,
        attrs: (group.attrs || []).filter(
          (item: any) =>
            !item?.is_system_link &&
            !['node_id', 'monitor_id'].includes(item?.attr_id)
        ),
      }))
      .filter((group: any) => (group.attrs || []).length > 0);
    setAttrList(list);
  }, [propertyList]);

  useEffect(() => {
    if (attrList.length) {
      const newAttrList = deepClone(attrList);
      initData(newAttrList);
    }
  }, [propertyList, instDetail, userList, attrList, collapsedTableFields]);

  const updateInst = async (config: {
    id: string;
    values: any;
    type: string;
  }) => {
    const fieldKey = config.id;
    const fieldAttr: any = attrList
      .flatMap((group: any) => group.attrs || [])
      .find((item: any) => item.attr_id === fieldKey);
    
    const fieldValue = normalizeFieldValue(fieldKey, config.values[fieldKey], fieldAttr);

    const params: any = { _scenario: editScenario };
    params[fieldKey] = fieldValue;
    await updateInstance(instUuid, params);
    message.success(t('successfullyModified'));
    const list = deepClone(attrList);

    for (const group of list) {
      const target = group.attrs?.find((item: any) => item.attr_id === fieldKey);
      if (target) {
        if (config.type === 'success' || (config.type === 'fail' && !target?.is_required)) {
          target.isEdit = false;
          target.value = fieldValue;
        }
        break;
      }
    }
    setAttrList(list);
    onsuccessEdit();
    useAssetDataStore.getState().setNeedRefresh(true);
  };

  const getEditableFieldValue = (fieldItem: any) =>
    fieldItem._originalValue ?? fieldItem.value;

  const normalizeFieldValue = (
    fieldKey: string,
    fieldValue: any,
    fieldAttr?: any
  ) => {
    let value = normalizeTimeValueForSubmit(fieldAttr, fieldValue);
    if (fieldAttr?.attr_type === 'organization' && value != null) {
      value = Array.isArray(value) ? value : [value];
    }
    if (fieldAttr?.attr_type === 'table' && Array.isArray(value)) {
      const filtered = value.filter((row: any) =>
        Object.values(row).some((v) => v !== '' && v !== null && v !== undefined)
      );
      value = filtered.length > 0 ? filtered : undefined;
    }
    if (fieldKey === 'cloud' || fieldKey === 'cloud_id') {
      return String(value);
    }
    return value;
  };
  const getAttrById = (id: string) =>
    attrList.flatMap((group: any) => group.attrs || []).find(
      (item: any) => item.attr_id === id
    );

  const toggleBatchEdit = (nextState: boolean) => {
    const list = deepClone(attrList);
    const values: any = {};

    list.forEach((group: any) => {
      (group.attrs || []).forEach((item: any) => {
        if (item.editable) {
          item.isEdit = nextState;
          if (nextState) {
            const rawValue = getEditableFieldValue(item);
            values[item.attr_id] = normalizeTimeValueForForm(item, rawValue);
          }
        }
      });
    });

    setAttrList(list);
    setIsBatchEdit(nextState);
    if (nextState) {
      form.setFieldsValue(values);
    }
  };

  const handleBatchCancel = () => {
    toggleBatchEdit(false);
    const resetValues: any = {};
    attrList.forEach((group: any) => {
      (group.attrs || []).forEach((item: any) => {
        const rawValue = getEditableFieldValue(item);
        resetValues[item.attr_id] = normalizeTimeValueForForm(item, rawValue);
      });
    });
    form.setFieldsValue(resetValues);
  };

  const handleBatchSave = async () => {
    setIsBatchSaving(true);
    try {
      const values = await form.validateFields();
      const params: any = {};

      Object.keys(values).forEach((key) => {
        const rawValue = values[key];
        if (rawValue === undefined) {
          return;
        }
        const fieldAttr = getAttrById(key);
        params[key] = normalizeFieldValue(key, rawValue, fieldAttr);
      });

      params._scenario = editScenario;
      await updateInstance(instUuid, params);
      message.success(t('successfullyModified'));

      const list = deepClone(attrList);
      list.forEach((group: any) => {
        (group.attrs || []).forEach((item: any) => {
          if (Object.prototype.hasOwnProperty.call(params, item.attr_id)) {
            item.value = params[item.attr_id];
          }
          if (item.isEdit) {
            item.isEdit = false;
          }
        });
      });

      setAttrList(list);
      setIsBatchEdit(false);
      onsuccessEdit();
      useAssetDataStore.getState().setNeedRefresh(true);
    } finally {
      setIsBatchSaving(false);
    }
  };

  const toggleTableFieldCollapse = (fieldKey: string) => {
    setCollapsedTableFields((prev) => ({
      ...prev,
      [fieldKey]: !prev[fieldKey],
    }));
  };

  const initData = (list: any) => {
    list.forEach((group: any) => {
      const itemList = group.attrs;
      itemList.forEach((item: any) => {
        const originalValue = item.value || instDetail[item.attr_id];
        item.value = originalValue;
        item.key = item.attr_id;
        const isTableFieldCollapsed = !!collapsedTableFields[item.attr_id];
        item.label = (
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              {item.attr_name}
              {item.is_required && <span className={informationList.required}></span>}
              {item.user_prompt && (
                <Tooltip title={item.user_prompt}>
                  <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
                </Tooltip>
              )}
            </div>
            {item.attr_type === 'table' && !item.isEdit && (
              <Button
                type="link"
                size="small"
                className="!h-auto !p-0 text-xs whitespace-nowrap"
                icon={isTableFieldCollapsed ? <DownOutlined /> : <UpOutlined />}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  toggleTableFieldCollapse(item.attr_id);
                }}
              >
                {isTableFieldCollapsed ? t('expandAll') : t('closeAll')}
              </Button>
            )}
          </div>
        );
        item.isEdit = item.isEdit || false;
        const formInitialValue = normalizeTimeValueForForm(item, item._originalValue ?? item.value);
        item.children = (
          <Form
            key={item.attr_id}
            form={form}
            onValuesChange={handleValuesChange}
          >
            <div
              key={item.key}
              className={`flex items-center ${informationList.formItem}`}
            >
              <div className="flex items-center flex-1 min-w-0">
                {item.isEdit ? (
                  <Form.Item
                    name={item.key}
                    rules={getValidationRules(item, t)}
                    initialValue={formInitialValue}
                    className="mb-0 w-full"
                  >
                    <>
                      {(
                        (item.attr_id === 'cloud' && modelId === 'host') ||
                        (item.attr_id === 'cloud_id' && modelId === 'subnet')
                      ) ? (
                        <Select placeholder={t('common.selectTip')}>
                          {cloudOptions.map((opt) => (
                            <Select.Option key={opt.proxy_id} value={opt.proxy_id}>
                              {opt.proxy_name}
                            </Select.Option>
                          ))}
                        </Select>
                        ) : (
                          getFieldItem({
                            fieldItem: item,
                            userList,
                            isEdit: true,
                            modelId,
                          })
                        )}
                    </>
                  </Form.Item>
                ) : (
                  <>
                    {item.attr_type === 'tag' ? (
                      <TagCapsuleGroup value={item.value} maxVisible={2} />
                    ) : item.attr_type === 'table' && collapsedTableFields[item.attr_id] ? (
                      <span className="text-[var(--color-text-3)]">--</span>
                    ) : (
                      getFieldItem({
                        fieldItem: item,
                        userList,
                        isEdit: false,
                        value: item.value,
                        modelId,
                      })
                    )}
                  </>
                )}
              </div>
              <div
                className={`flex flex-shrink-0 ${informationList.operateBtn} ${item.isEdit && item.attr_type === 'table' ? 'items-start self-start' : 'items-center'}`}
              >
                {item.isEdit ? (
                  <>
                    {!isBatchEdit && (
                      <>
                        <Button
                          type="link"
                          size="small"
                          className="ml-[4px]"
                          aria-label={t('common.confirm')}
                          icon={<CheckOutlined aria-hidden="true" />}
                          onClick={() => confirmEdit(item.key)}
                        />
                        <Button
                          type="link"
                          size="small"
                          aria-label={t('common.cancel')}
                          icon={<CloseOutlined aria-hidden="true" />}
                          onClick={() => cancelEdit(item.key)}
                        />
                      </>
                    )}
                  </>
                ) : (
                  <>
                    {item.editable && (
                      <PermissionWrapper
                        requiredPermissions={['Edit']}
                        instPermissions={instDetail.permission}
                      >
                        <Button
                          type="link"
                          size="small"
                          className="ml-[4px]"
                          aria-label={t('common.edit')}
                          icon={<EditOutlined aria-hidden="true" />}
                          onClick={() => enableEdit(item.key)}
                        />
                      </PermissionWrapper>
                    )}
                    <Button
                      type="link"
                      size="small"
                      aria-label={t('common.copy')}
                      icon={<CopyOutlined aria-hidden="true" />}
                      onClick={() => onCopy(item, item.value)}
                    />
                  </>
                )}
              </div>
            </div>
          </Form>
        );
        if (item.attr_type === 'table') {
          item.span = 2;
        }
      });
    })

    setFieldList(list);
  };

  const enableEdit = (id: string) => {
    if (isBatchEdit) {
      return;
    }
    const list = deepClone(attrList);
    for (const group of list) {
      const attr = group.attrs?.find((item: any) => item.attr_id === id);
      if (attr) {
        attr.isEdit = true;
        break;
      }
    }
    setAttrList(list);
  };

  const cancelEdit = (id: string) => {
    if (isBatchEdit) {
      return;
    }
    const list = deepClone(attrList);
    for (const group of list) {
      const attr = group.attrs?.find((item: any) => item.attr_id === id);
      if (attr) {
        attr.isEdit = false;
        const obj: any = {};
        obj[id] = normalizeTimeValueForForm(attr, attr._originalValue ?? attr.value);
        form.setFieldsValue(obj);
        break;
      }
    }
    setAttrList(list);
  };

  const handleValuesChange = () => {};

  const confirmEdit = (id: string) => {
    if (isBatchEdit) {
      return;
    }
    form
      .validateFields()
      .then((values) => {
        onFinish(values, id);
      })
      .catch(({ values }) => {
        onFailFinish(values, id);
      });
  };

  const onFinish = (values: any, id: string) => {
    updateInst({
      values,
      id,
      type: 'success',
    });
  };

  const onFailFinish = (values: any, id: string) => {
    updateInst({
      values,
      id,
      type: 'fail',
    });
  };

  const onCopy = (item: any, value: string) => {
    const copyVal: string = getFieldItem({
      fieldItem: item,
      userList,
      isEdit: false,
      value,
      hideUserAvatar: true,
      flatGroups,
      modelId,
    }) as string;
    navigator.clipboard.writeText(copyVal);
    message.success(t('successfulCopied'));
  };

  const organizationAttrs: any[] = [];
  const otherGroups = fieldList.map((group: any) => {
    const organizationItems = (group.attrs || []).filter(
      (attr: any) => attr.attr_id === 'organization'
    );
    const otherAttrs = (group.attrs || []).filter(
      (attr: any) => attr.attr_id !== 'organization'
    );

    if (organizationItems.length > 0) {
      organizationAttrs.push(...organizationItems);
    }

    return {
      ...group,
      attrs: otherAttrs,
    };
  }).filter((group: any) => group.attrs && group.attrs.length > 0);

  const displayGroups = [];
  if (organizationAttrs.length > 0) {
    displayGroups.push({
      id: 'organization-group',
      group_name: t('common.group'),
      attrs: organizationAttrs,
      is_collapsed: false,
    });
  }

  displayGroups.push(...otherGroups);

  const hasEditableField = attrList.some((group: any) =>
    (group.attrs || []).some(
      (item: any) => item.editable
    )
  );

  const showSystemLinkage =
    canSyncMonitor(modelId) ||
    instDetail?.node_id ||
    instDetail?.monitor_id;
  const systemLinkageItems = showSystemLinkage
    ? [
      ...(showNodeId(modelId)
        ? [
          {
            key: 'node_id',
            label: t('Model.systemLinkageNodeId'),
            children: (
              <span className="font-mono text-[13px] break-all">
                {instDetail?.node_id || t('Model.systemLinkageEmpty')}
              </span>
            ),
          },
        ]
        : []),
      {
        key: 'monitor_id',
        label: t('Model.systemLinkageMonitorId'),
        children: (
          <span className="font-mono text-[13px] break-all">
            {instDetail?.monitor_id || t('Model.systemLinkageEmpty')}
          </span>
        ),
      },
    ]
    : [];

  const handleSyncMonitor = async () => {
    setIsSyncingMonitor(true);
    try {
      const res = await pushToMonitor(instUuid);
      const key = resolveMonitorLinkMessage(res);
      const text = t(key);
      const status = res?.link_status;
      if (status === 'ok') {
        message.success(text);
        onsuccessEdit?.();
      } else if (status === 'not_found' || status === 'conflict') {
        message.warning(text);
      } else {
        message.error(text);
      }
    } catch {
      message.error(t('Model.systemLinkageSyncFailed'));
    } finally {
      setIsSyncingMonitor(false);
    }
  };

  return (
    <div>
      {hasEditableField && (
        <div className="flex items-center justify-end mb-2">
          {isBatchEdit ? (
            <>
              <span className="mr-1 text-[12px] text-[var(--color-text-3)]">
                {t('OperationLog.scenario')}:
              </span>
              <Select
                size="small"
                style={{ width: 140 }}
                className="mr-2"
                value={editScenario}
                onChange={(val) => setEditScenario(val)}
                options={[
                  {
                    label: t('OperationLog.scenarioOpts.ordinary_attribute_change'),
                    value: 'ordinary_attribute_change',
                  },
                  {
                    label: t('OperationLog.scenarioOpts.device_lifecycle'),
                    value: 'device_lifecycle',
                  },
                ]}
              />
              <Button
                type="primary"
                size="small"
                loading={isBatchSaving}
                className="mr-2"
                onClick={handleBatchSave}
              >
                {t('common.save')}
              </Button>
              <Button size="small" onClick={handleBatchCancel}>
                {t('common.cancel')}
              </Button>
            </>
          ) : (
            <>
              <Button
                size="small"
                icon={<BellOutlined />}
                className="mr-2"
                onClick={onSubscribe}
              >
                {t('subscription.subscribe')}
              </Button>
              <PermissionWrapper
                requiredPermissions={['Edit']}
                instPermissions={instDetail.permission}
              >
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => toggleBatchEdit(true)}
                >
                  {t('batchEdit')}
                </Button>
              </PermissionWrapper>
            </>
          )}
        </div>
      )}
      {displayGroups && displayGroups.length > 0 && (
        <Collapse
          style={{ background: 'var(--color-bg-1) ' }}
          bordered={false}
          className={informationList.list}
          defaultActiveKey={displayGroups
            .filter((item: any) => !item.is_collapsed)
            .map((item: any) => String(item.id))}
          expandIcon={({ isActive }) => (
            <CaretRightOutlined rotate={isActive ? 90 : 0} />
          )}
        >
          {displayGroups.map((group: any) => {
            return (
              <Panel
                key={String(group.id)}
                header={group.group_name}
              >
                <Descriptions
                  bordered
                  items={group.attrs || []}
                  column={2}
                />
              </Panel>
            )
          })}
        </Collapse>
      )}
      {showSystemLinkage && (
        <div className="mt-4 rounded border border-[var(--color-border-2)] bg-[var(--color-bg-2)] px-4 py-3">
          <div className="mb-1 flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-[var(--color-text-1)]">
              {t('Model.systemLinkage')}
            </div>
            {canSyncMonitor(modelId) && isMonitorSold(clientData) && (
              <PermissionWrapper
                requiredPermissions={['Edit']}
                instPermissions={instDetail.permission}
              >
                <Button
                  size="small"
                  icon={<SyncOutlined />}
                  loading={isSyncingMonitor}
                  onClick={handleSyncMonitor}
                >
                  {t('Model.systemLinkageSync')}
                </Button>
              </PermissionWrapper>
            )}
          </div>
          <div className="mb-3 text-xs text-[var(--color-text-3)]">
            {t('Model.systemLinkageHint')}
          </div>
          <Descriptions bordered size="small" column={1} items={systemLinkageItems} />
        </div>
      )}
    </div>
  );
};

export default InfoList;
