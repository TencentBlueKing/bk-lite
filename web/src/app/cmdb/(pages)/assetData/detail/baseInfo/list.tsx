import React, { useState, useEffect } from 'react';
import informationList from './list.module.scss';
import { Form, Button, Collapse, Descriptions, message, Select } from 'antd';
import { deepClone, getFieldItem } from '@/app/cmdb/utils/common';
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
} from '@ant-design/icons';
import { useInstanceApi } from '@/app/cmdb/api';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

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

  const { updateInstance, getInstanceProxys } = useInstanceApi();

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

  // 获取云区域列表
  const cloudOptions = (useAssetDataStore.getState().cloud_list || []).map((item: any) => ({
    proxy_id: String(item.proxy_id),
    proxy_name: item.proxy_name,
  }));

  useEffect(() => {
    // 详情页中当模型为host时，获取云区域
    if (modelId == 'host') {
      getInstanceProxys()
        .then((data: any[]) => {

          // 保存云区域列表到前端store
          useAssetDataStore.getState().setCloudList(data || []);
        })
        .catch(() => {
          console.error('获取云区域列表失败');
        });
    }
  }, []);

  useEffect(() => {
    // propertyList是模型属性列表+值
    // console.log("test7.4", propertyList);

    // 深拷贝避免修改原始数据
    const list = deepClone(propertyList);

    setAttrList(list);
  }, [propertyList]);

  useEffect(() => {
    if (attrList.length) {

      // 深拷贝避免修改原始数据
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
    let fieldValue = config.values[fieldKey];

    // 从分组结构中查找属性
    const fieldAttr: any = attrList
      .flatMap((group: any) => group.attrs || [])
      .find((item: any) => item.attr_id === fieldKey);
    if (fieldAttr?.attr_type === 'organization' && fieldValue != null) {
      fieldValue = Array.isArray(fieldValue) ? fieldValue : [fieldValue];
    }

    const params: any = {};
    // 规范云区域提交参数
    if (fieldKey === 'cloud') {
      params[fieldKey] = String(fieldValue);
    } if (fieldKey === 'cloud_id') {
      params[fieldKey] = +fieldValue;
    } else {
      params[fieldKey] = fieldValue;
    }
    await updateInstance(instId, params);
    message.success(t('successfullyModified'));
    const list = deepClone(attrList);

    // 从分组结构中查找并更新属性的编辑
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
  };

  // 获取可以编辑的值
  const getEditableFieldValue = (fieldItem: any) =>
    fieldItem._originalValue ?? fieldItem.value;


  const normalizeFieldValue = (
    fieldKey: string,
    fieldValue: any,
    fieldAttr?: any
  ) => {
    let value = fieldValue;
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
            values[item.attr_id] = getEditableFieldValue(item);
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
        resetValues[item.attr_id] = getEditableFieldValue(item);
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
    } finally {
      setIsBatchSaving(false);
    }
  };

  const initData = (list: any) => {
    // 遍历分组，得到每组列表
    list.forEach((item: any) => {
      const itemList = item.attrs;

      // 遍历每组列表，得到每个属性
      itemList.forEach((item: any) => {
        // 获取原始值 + 把原始值赋值给 value（用于正常情况下的渲染）
        const originalValue = item.value || instDetail[item.attr_id];
        item.value = originalValue;

        // 特殊处理-主机的云区域显示中文名称（初始化时）
        if (item.attr_id === 'cloud' && modelId === 'host') {
          const cloudId = String(originalValue);
          const cloudName = cloudOptions.find(
            (option: any) => option.proxy_id === cloudId
          );
          // 如果找到匹配项，将 item.value 设置为中文名字
          if (cloudName) {
            item.value = cloudName.proxy_name;
            item._originalValue = cloudId;
          } else if (originalValue) {
            // 如果找不到匹配项，保存原始值用于后续匹配
            item._originalValue = cloudId;
          }
        }
        item.key = item.attr_id;
        item.label = item.is_required ? (
          <>
            {item.attr_name}
            <span className={informationList.required}></span>
          </>
        ) : (
          <>{item.attr_name}</>
        );
        item.isEdit = item.isEdit || false;
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
                    rules={[
                      {
                        required: item.is_required,
                        message: '',
                      },
                    ]}
                    // 编辑提交时，如果是云区域字段会用_originalValue的值（用于提交id数字字符串）
                    initialValue={item._originalValue || item.value}
                    className="mb-0 w-full"
                  >
                    <>
                      {/* 特殊处理-主机的云区域为下拉选项（详情页中） */}
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
                    {/* cloud_id 字段不允许编辑 */}
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
    // 通过for循环遍历分组，找到对应的属性并设置编辑状态
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
    // 通过for循环遍历分组，恢复表单值为修改前的原始值
    for (const group of list) {
      const attr = group.attrs?.find((item: any) => item.attr_id === id);
      if (attr) {
        attr.isEdit = false;
        const obj: any = {};
        obj[id] = attr.value;
        form.setFieldsValue(obj);
        break;
      }
    }
    setAttrList(list);
  };

  // 处理字段值变化的回调函数
  const handleValuesChange = (changedValues: any,) => {
    // 当云区域（cloud）变化时，自动更新云区域ID（cloud_id）
    if (changedValues.cloud !== undefined && modelId === 'host') {
      const cloudId = changedValues.cloud;
      // 将 cloud_id 设置为 cloud 的值（cloud_id为数字格式，cloud为字符串格式）
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
    });
    navigator.clipboard.writeText(copyVal);
    message.success(t('successfulCopied'));
  };

  // 提取 organization 字段并分离其他字段
  const organizationAttrs: any[] = [];
  const otherGroups = fieldList.map((group: any) => {
    //我猜可能不止一个组织字段，所以需要过滤出 organization 字段
    const organizationItems = (group.attrs || []).filter(
      (attr: any) => attr.attr_id === 'organization'
    );
    const otherAttrs = (group.attrs || []).filter(
      (attr: any) => attr.attr_id !== 'organization'
    );

    // 提取 organization 字段
    if (organizationItems.length > 0) {
      organizationAttrs.push(...organizationItems);
    }

    // 返回其他字段
    return {
      ...group,
      attrs: otherAttrs,
    };
  }).filter((group: any) => group.attrs && group.attrs.length > 0);

  // 合并所有需要显示的分组
  const displayGroups = [];
  if (organizationAttrs.length > 0) {
    displayGroups.push({
      id: 'organization-group',
      group_name: t('common.group'),
      attrs: organizationAttrs,
      is_collapsed: false,
    });
  }

  // 合并其他字段
  displayGroups.push(...otherGroups);

  // 渲染详情页
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
            // 遍历分组，得到最终的每组列表
            // console.log("test8.16:group", group);
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