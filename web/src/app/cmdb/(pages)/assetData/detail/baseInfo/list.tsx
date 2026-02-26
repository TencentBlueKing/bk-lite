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
  CopyOutlined,
  CheckOutlined,
  CloseOutlined,
  CaretRightOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { useInstanceApi } from '@/app/cmdb/api';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import { useUserInfoContext } from '@/context/userInfo';

const { Panel } = Collapse;
const InfoList: React.FC<AssetDataFieldProps> = ({
  propertyList,
  userList,
  instDetail,
  onsuccessEdit,
}) => {
  const [form] = Form.useForm();
  const [fieldList, setFieldList] = useState<DescriptionsProps['items']>([]);
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [isBatchEdit, setIsBatchEdit] = useState<boolean>(false);
  const [isBatchSaving, setIsBatchSaving] = useState<boolean>(false);
  const { t } = useTranslation();
  const { flatGroups } = useUserInfoContext();

  const { updateInstance, getInstanceProxys } = useInstanceApi();

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

  const cloudOptions = (useAssetDataStore.getState().cloud_list || []).map((item: any) => ({
    proxy_id: String(item.proxy_id),
    proxy_name: item.proxy_name,
  }));

  useEffect(() => {
    if (modelId == 'host') {
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
    const list = deepClone(propertyList);
    setAttrList(list);
  }, [propertyList]);

  useEffect(() => {
    if (attrList.length) {
      const newAttrList = deepClone(attrList);
      initData(newAttrList);
    }
  }, [propertyList, instDetail, userList, attrList]);

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

    const params: any = {};
    params[fieldKey] = fieldValue;
    await updateInstance(instId, params);
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
    if (fieldKey === 'cloud') {
      return String(value);
    }
    if (fieldKey === 'cloud_id') {
      return value == null ? value : +value;
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
        if (item.editable && item.attr_id !== 'cloud_id') {
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

      await updateInstance(instId, params);
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

  const initData = (list: any) => {
    list.forEach((item: any) => {
      const itemList = item.attrs;

      itemList.forEach((item: any) => {
        const originalValue = item.value || instDetail[item.attr_id];
        item.value = originalValue;

        if (item.attr_id === 'cloud' && modelId === 'host') {
          const cloudId = String(originalValue);
          const cloudName = cloudOptions.find(
            (option: any) => option.proxy_id === cloudId
          );
          if (cloudName) {
            item.value = cloudName.proxy_name;
            item._originalValue = cloudId;
          } else if (originalValue) {
            item._originalValue = cloudId;
          }
        }
        item.key = item.attr_id;
        item.label = (
          <>
            {item.attr_name}
            {item.is_required && <span className={informationList.required}></span>}
            {item.user_prompt && (
              <Tooltip title={item.user_prompt}>
                <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
              </Tooltip>
            )}
          </>
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
              className={`flex items-center justify-between ${informationList.formItem}`}
            >
              <div className="flex items-center w-full">
                {item.isEdit ? (
                  <Form.Item
                    name={item.key}
                    rules={getValidationRules(item, t)}
                    initialValue={formInitialValue}
                    className="mb-0 w-full"
                  >
                    <>
                      {item.attr_id === 'cloud' && modelId === 'host' ? (
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
                        })
                      )}
                    </>
                  </Form.Item>
                ) : (
                  <>
                    {getFieldItem({
                      fieldItem: item,
                      userList,
                      isEdit: false,
                      value: item.value,
                    })}
                  </>
                )}
              </div>
              <div className={`flex items-center ${informationList.operateBtn}`}>
                {item.isEdit ? (
                  <>
                    {!isBatchEdit && (
                      <>
                        <Button
                          type="link"
                          size="small"
                          className="ml-[4px]"
                          icon={<CheckOutlined />}
                          onClick={() => confirmEdit(item.key)}
                        />
                        <Button
                          type="link"
                          size="small"
                          icon={<CloseOutlined />}
                          onClick={() => cancelEdit(item.key)}
                        />
                      </>
                    )}
                  </>
                ) : (
                  <>
                    {item.editable && item.attr_id !== 'cloud_id' && (
                      <PermissionWrapper
                        requiredPermissions={['Edit']}
                        instPermissions={instDetail.permission}
                      >
                        <Button
                          type="link"
                          size="small"
                          className="ml-[4px]"
                          icon={<EditOutlined />}
                          onClick={() => enableEdit(item.key)}
                        />
                      </PermissionWrapper>
                    )}
                    <Button
                      type="link"
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => onCopy(item, item.value)}
                    />
                  </>
                )}
              </div>
            </div>
          </Form>
        );
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

  const handleValuesChange = (changedValues: any,) => {
    if (changedValues.cloud !== undefined && modelId === 'host') {
      const cloudId = changedValues.cloud;
      form.setFieldsValue({
        cloud_id: cloudId ? Number(cloudId) : undefined,
      });
    }
  };

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
    });
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
      (item: any) => item.editable && item.attr_id !== 'cloud_id'
    )
  );

  return (
    <div>
      {hasEditableField && (
        <div className="flex items-center justify-end mb-2">
          {isBatchEdit ? (
            <>
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
          )}
        </div>
      )}
      {/* 通过遍历 fieldList，自动添加Collapse折叠面板容器，并设置默认展开 */}
      {displayGroups && displayGroups.length > 0 && (
        <Collapse
          style={{ background: 'var(--color-bg-1) ' }}
          bordered={false}
          className={informationList.list}
          // accordion // 手风琴效果先不用，看后面需求来决定是否使用
          // 默认展开的相关逻辑（后端传一个默认展开的id数组）
          defaultActiveKey={displayGroups
            .filter((item: any) => !item.is_collapsed)
            .map((item: any) => String(item.id))}
          // 折叠面板的展开图标
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
    </div>
  );
};

export default InfoList;