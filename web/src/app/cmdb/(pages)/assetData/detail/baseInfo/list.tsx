import React, { useState, useEffect } from 'react';
import informationList from './list.module.scss';
import { Form, Button, Collapse, Descriptions, message } from 'antd';
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
  const { t } = useTranslation();

  const { updateInstance } = useInstanceApi();

  const searchParams = useSearchParams();
  const instId: string = searchParams.get('inst_id') || '';

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
    params[fieldKey] = fieldValue;
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

  const initData = (list: any) => {
    // 遍历分组，得到每组列表
    list.forEach((item: any) => {
      const itemList = item.attrs;

      // 遍历每组列表，得到每个属性
      itemList.forEach((item: any) => {
        item.value = item.value || instDetail[item.attr_id];
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
          <Form key={item.attr_id} form={form}>
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
                    initialValue={item.value}
                    className="mb-0 w-full"
                  >
                    <>
                      {getFieldItem({
                        fieldItem: item,
                        userList,
                        isEdit: true,
                      })}
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

  const confirmEdit = (id: string) => {
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

  return (
    <div>
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
          {displayGroups.map((group: any) => (
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
          ))}
        </Collapse>
      )}
    </div >
  );
};

export default InfoList;