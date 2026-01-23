'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import {
  Input,
  InputNumber,
  Button,
  Form,
  message,
  Select,
  DatePicker,
  Col,
  Row,
  Checkbox,
} from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import { AttrFieldType, UserItem, FullInfoGroupItem, FullInfoAttrItem, FieldConfig } from '@/app/cmdb/types/assetManage';
import { deepClone } from '@/app/cmdb/utils/common';
import { useInstanceApi } from '@/app/cmdb/api';
import dayjs from 'dayjs';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import styles from './FilterBar.module.scss';

interface FieldModalProps {
  onSuccess: (instId?: string) => void;
  userList: UserItem[];
}

export interface FieldModalRef {
  showModal: (info: FieldConfig) => void;
}

const FieldMoadal = forwardRef<FieldModalRef, FieldModalProps>(
  ({ onSuccess, userList }, ref) => {
    const { selectedGroup } = useUserInfoContext();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [formItems, setFormItems] = useState<FullInfoGroupItem[]>([]);
    const [instanceData, setInstanceData] = useState<any>({});
    const [selectedRows, setSelectedRows] = useState<any[]>([]);
    const [modelId, setModelId] = useState<string>('');
    const [enabledFields, setEnabledFields] = useState<Record<string, boolean>>(
      {}
    );
    const [proxyOptions, setProxyOptions] = useState<
      { proxy_id: string; proxy_name: string }[]
    >([]);
    const [form] = Form.useForm();
    const { t } = useTranslation();
    const instanceApi = useInstanceApi();

    useEffect(() => {
      if (groupVisible) {
        setEnabledFields({});
        form.resetFields();
        form.setFieldsValue(instanceData);
      }
    }, [groupVisible, instanceData]);

    useEffect(() => {
      if (groupVisible && modelId === 'host') {
        instanceApi
          .getInstanceProxys()
          .then((data: any[]) => {
            setProxyOptions(data || []);
          })
          .catch(() => {
            setProxyOptions([]);
          });
      }
    }, [groupVisible, modelId]);

    // 监听 ip_addr 和 cloud，自动填充 inst_name
    const ipValue = Form.useWatch('ip_addr', form);
    const cloudValue = Form.useWatch('cloud', form);
    useEffect(() => {
      if (modelId === 'host') {
        const cloudName = proxyOptions.find(
          (opt) => opt.proxy_id === cloudValue
        )?.proxy_name;
        if (ipValue && cloudName) {
          form.setFieldsValue({
            inst_name: `${ipValue || ''}[${cloudName || ''}]`,
          });
        }
      }
    }, [ipValue, cloudValue, modelId, proxyOptions]);

    useImperativeHandle(ref, () => ({
      showModal: ({
        type,
        attrList,
        subTitle,
        title,
        formInfo,
        model_id,
        list,
      }) => {
        // 打印属性标题列表+值
        // console.log('test7.9', attrList);

        // 开启弹窗的交互
        setGroupVisible(true);
        setSubTitle(subTitle);
        setType(type);
        setTitle(title);
        setModelId(model_id);
        setFormItems(attrList);
        setSelectedRows(list);
        const forms = deepClone(formInfo);

        // 提取所有属性并扁平化，用于在315行数据中查找
        const allAttrs = attrList.flatMap((group) => group.attrs || []);

        // 转换日期和组织字段格式（复制和编辑都需要）
        for (const key in forms) {
          const target = allAttrs.find((item: FullInfoAttrItem) => item.attr_id === key);
          if (target?.attr_type === 'time' && forms[key]) {
            forms[key] = dayjs(forms[key], 'YYYY-MM-DD HH:mm:ss');
          } else if (target?.attr_type === 'organization' && forms[key]) {
            forms[key] = forms[key]
              .map((item: any) => Number(item))
              .filter((num: number) => !isNaN(num));
          }
        }

        // 复制操作时，覆盖组织字段为当前选中的分组
        if (type === 'add') {
          Object.assign(forms, {
            organization: selectedGroup?.id
              ? [Number(selectedGroup.id)]
              : undefined,
          });
        }
        setInstanceData(forms);
      },
    }));

    const handleFieldToggle = (fieldId: string, enabled: boolean) => {
      setEnabledFields((prev) => ({
        ...prev,
        [fieldId]: enabled,
      }));

      if (!enabled) {
        form.setFieldValue(fieldId, undefined);
      }
    };

    const renderFormLabel = (item: FullInfoAttrItem) => {
      return (
        <div className="flex items-center">
          {type === 'batchEdit' && item.editable && !item.is_only ? (
            <Checkbox
              checked={enabledFields[item.attr_id]}
              onChange={(e) =>
                handleFieldToggle(item.attr_id, e.target.checked)
              }
            >
              <span>{item.attr_name}</span>
            </Checkbox>
          ) : (
            <span className="ml-2">{item.attr_name}</span>
          )}
          {item.is_required && type !== 'batchEdit' && (
            <span className="text-[#ff4d4f] ml-1">*</span>
          )}
        </div>
      );
    };

    const renderFormField = (item: FullInfoAttrItem) => {
      const fieldDisabled =
        type === 'batchEdit'
          ? !enabledFields[item.attr_id]
          : !item.editable && type !== 'add';

      const hostDisabled = modelId === 'host' && item.attr_id === 'inst_name';

      const formField = (() => {
        // 特殊处理-主机的云区域为下拉选项
        if (item.attr_id === 'cloud') {
          return (
            <Select
              disabled={fieldDisabled}
              placeholder={t('common.selectTip')}
            >
              {proxyOptions.map((opt) => (
                <Select.Option key={opt.proxy_id} value={opt.proxy_id}>
                  {opt.proxy_name}
                </Select.Option>
              ))}
            </Select>
          );
        }
        // 新增+编辑弹窗中，用户字段为多选
        switch (item.attr_type) {
          case 'user':
            return (
              <Select
                mode="multiple"
                showSearch
                disabled={fieldDisabled}
                placeholder={t('common.selectTip')}
                filterOption={(input, opt: any) => {
                  if (typeof opt?.children?.props?.text === 'string') {
                    return opt?.children?.props?.text
                      ?.toLowerCase()
                      .includes(input.toLowerCase());
                  }
                  return true;
                }}
              >
                {userList.map((opt: UserItem) => (
                  <Select.Option key={opt.id} value={opt.id}>
                    <EllipsisWithTooltip
                      text={`${opt.display_name}(${opt.username})`}
                      className="whitespace-nowrap overflow-hidden text-ellipsis break-all"
                    />
                  </Select.Option>
                ))}
              </Select>
            );
          case 'enum':
            return (
              <Select
                showSearch
                disabled={fieldDisabled}
                placeholder={t('common.selectTip')}
                filterOption={(input, opt: any) => {
                  if (typeof opt?.children === 'string') {
                    return opt?.children
                      ?.toLowerCase()
                      .includes(input.toLowerCase());
                  }
                  return true;
                }}
              >
                {(Array.isArray(item.option) ? item.option : item.option ? JSON.parse(item.option) : []).map((opt: any) => (
                  <Select.Option key={opt.id} value={opt.id}>
                    {opt.name}
                  </Select.Option>
                ))}
              </Select>
            );
          case 'bool':
            return (
              <Select
                disabled={fieldDisabled}
                placeholder={t('common.selectTip')}
              >
                {[
                  { id: true, name: 'Yes' },
                  { id: false, name: 'No' },
                ].map((opt) => (
                  <Select.Option key={opt.id.toString()} value={opt.id}>
                    {opt.name}
                  </Select.Option>
                ))}
              </Select>
            );
          case 'time':
            return (
              <DatePicker
                placeholder={t('common.selectTip')}
                showTime
                disabled={fieldDisabled}
                format="YYYY-MM-DD HH:mm:ss"
                style={{ width: '100%' }}
              />
            );
          case 'organization':
            return (
              <GroupTreeSelector multiple={true} disabled={fieldDisabled} />
            );
          case 'int':
            return (
              <InputNumber
                disabled={fieldDisabled}
                style={{ width: '100%' }}
                placeholder={t('common.inputTip')}
              />
            );
          default:
            return (
              <Input
                placeholder={t('common.inputTip')}
                disabled={fieldDisabled || hostDisabled}
              />
            );
        }
      })();

      return formField;
    };

    const handleSubmit = (confirmType?: string) => {
      form
        .validateFields()
        .then((values) => {
          // 从分组中提取所有属性并扁平化，用于在315行数据中查找
          const allAttrs = formItems.flatMap((group) => group.attrs || []);
          for (const key in values) {
            const target = allAttrs.find((item: FullInfoAttrItem) => item.attr_id === key);
            if (target?.attr_type === 'time' && values[key]) {
              values[key] = values[key].format('YYYY-MM-DD HH:mm:ss');
            }
          }
          operateAttr(values, confirmType);
        })
        .catch((errorInfo) => {
          if (errorInfo.errorFields && errorInfo.errorFields.length > 0) {
            const firstErrorField = errorInfo.errorFields[0].name[0];
            form.scrollToField(firstErrorField, {
              behavior: 'smooth',
              block: 'center',
            });
          }
        });
    };

    const operateAttr = async (params: AttrFieldType, confirmType?: string) => {
      try {
        const isBatchEdit = type === 'batchEdit';
        if (isBatchEdit) {
          const hasEnabledFields = Object.values(enabledFields).some(
            (enabled) => enabled
          );
          if (!hasEnabledFields) {
            message.warning(t('common.inputTip'));
            return;
          }
        }
        setConfirmLoading(true);
        let formData = null;
        if (isBatchEdit) {
          formData = Object.keys(params).reduce((acc, key) => {
            if (enabledFields[key]) {
              acc[key] = params[key];
            }
            return acc;
          }, {} as any);
        } else {
          formData = params;
        }
        const msg: string = t(
          type === 'add' ? 'successfullyAdded' : 'successfullyModified'
        );
        let result: any;
        if (type === 'add') {
          result = await instanceApi.createInstance({
            model_id: modelId,
            instance_info: formData,
          });
        } else {
          result = await instanceApi.batchUpdateInstances({
            inst_ids: type === 'edit' ? [instanceData._id] : selectedRows,
            update_data: formData,
          });
        }
        const instId = result?._id;
        message.success(msg);
        onSuccess(confirmType ? instId : '');
        handleCancel();
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    return (
      <div>
        <OperateModal
          title={title}
          subTitle={subTitle}
          open={groupVisible}
          width={730}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                onClick={() => handleSubmit()}
              >
                {t('common.confirm')}
              </Button>
              {type === 'add' && (
                <Button
                  className="mr-[10px]"
                  loading={confirmLoading}
                  onClick={() => handleSubmit('associate')}
                >
                  {t('Model.confirmAndAssociate')}
                </Button>
              )}
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          {/* 编辑弹窗的内容部分 */}
          <Form form={form} layout="vertical">
            {/* 遍历所有提取 organization 字段 */}
            {(() => {
              const organizationAttrs = formItems.flatMap((group) =>
                (group.attrs || []).filter((attr) => attr.attr_id === 'organization')
              );

              // 返回 organization 字段的数据
              return (
                <>
                  <div className={styles.groupOrganization}>
                    {t('common.group')}
                  </div>
                  <Row gutter={24}>
                    {organizationAttrs.map((item) => (
                      <Col span={12} key={item.attr_id}>
                        <Form.Item
                          className="mb-4"
                          name={item.attr_id}
                          label={renderFormLabel(item)}
                          rules={[
                            {
                              required: item.is_required && type !== 'batchEdit',
                              message: t('required'),
                            },
                          ]}
                        >
                          {renderFormField(item)}
                        </Form.Item>
                      </Col>
                    ))}
                  </Row>
                </>
              )
            })()}

            {/* 其他分组（不包含 organization 字段） */}
            {formItems.map((group) => {
              const otherAttrs = (group.attrs || []).filter(
                (attr) => attr.attr_id !== 'organization'
              );
              if (otherAttrs.length === 0) return null;

              // 返回其他分组的数据
              return (
                <div key={group.id}>
                  <div className={styles.groupOther}>
                    {group.group_name}
                  </div>
                  <Row gutter={24}>
                    {otherAttrs.map((item) => (
                      <Col span={12} key={item.attr_id}>
                        <Form.Item
                          className="mb-4"
                          name={item.attr_id}
                          label={renderFormLabel(item)}
                          rules={[
                            {
                              required: item.is_required && type !== 'batchEdit',
                              message: t('required'),
                            },
                          ]}
                        >
                          {renderFormField(item)}
                        </Form.Item>
                      </Col>
                    ))}
                  </Row>
                </div>
              );
            })}
          </Form>
        </OperateModal>
      </div>
    );
  }
);
FieldMoadal.displayName = 'fieldMoadal';
export default FieldMoadal;
