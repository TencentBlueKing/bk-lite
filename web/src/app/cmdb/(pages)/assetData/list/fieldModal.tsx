'use client';

import {
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
  Tooltip,
} from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import { AttrFieldType, UserItem, FullInfoGroupItem, FullInfoAttrItem, FieldConfig, StrAttrOption, TimeAttrOption, IntAttrOption } from '@/app/cmdb/types/assetManage';
import { deepClone } from '@/app/cmdb/utils/common';
import { useInstanceApi } from '@/app/cmdb/api';
import dayjs from 'dayjs';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import styles from './filterBar.module.scss';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

// 字符串验证正则表达式
const VALIDATION_PATTERNS: Record<string, RegExp> = {
  ipv4: /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
  ipv6: /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(([0-9a-fA-F]{1,4}:){1,6}|:):((:[0-9a-fA-F]{1,4}){1,6}|:)|::([fF]{4}(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/,
  email: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/,
  mobile_phone: /^1[3-9]\d{9}$/,
  url: /^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$/,
  json: /^[\s]*(\{[\s\S]*\}|\[[\s\S]*\])[\s]*$/,
};

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
        setProxyOptions(useAssetDataStore.getState().cloud_list || []);
      }
    }, [groupVisible, modelId]);

    const ipValue = Form.useWatch('ip_addr', form);
    const cloudValue = Form.useWatch('cloud', form);
    useEffect(() => {
      if (modelId === 'host') {
        const cloudName = proxyOptions.find(
          (opt: any) => opt.proxy_id === +cloudValue,
        )?.proxy_name;
        if (ipValue && cloudName) {
          form.setFieldsValue({
            inst_name: `${ipValue || ''}[${cloudName || ''}]`,
            cloud_id: Number(cloudValue),
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
        setGroupVisible(true);
        setSubTitle(subTitle);
        setType(type);
        setTitle(title);
        setModelId(model_id);
        setFormItems(attrList);
        setSelectedRows(list);
        const forms = deepClone(formInfo);

        const allAttrs = attrList.flatMap((group) => group.attrs || []);

        for (const key in forms) {
          const target = allAttrs.find(
            (item: FullInfoAttrItem) => item.attr_id === key,
          );
          if (target?.attr_type === 'time' && forms[key]) {
            forms[key] = dayjs(forms[key], 'YYYY-MM-DD HH:mm:ss');
          } else if (target?.attr_type === 'organization' && forms[key]) {
            forms[key] = forms[key]
              .map((item: any) => Number(item))
              .filter((num: number) => !isNaN(num));
          }
        }

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
      const labelContent = (
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
          {item.user_prompt && (
            <Tooltip title={item.user_prompt}>
              <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
            </Tooltip>
          )}
        </div>
      );
      return labelContent;
    };

    // 生成字符串验证规则
    const getStringValidationRule = (item: FullInfoAttrItem) => {
      const strOption = item.option as StrAttrOption;
      if (!strOption?.validation_type || strOption.validation_type === 'unrestricted') {
        return null;
      }

      if (strOption.validation_type === 'custom' && strOption.custom_regex) {
        try {
          return {
            pattern: new RegExp(strOption.custom_regex),
            message: t('Model.customRegexRequired'),
          };
        } catch {
          console.error('Invalid custom regex:', strOption.custom_regex);
          return null;
        }
      }

      if (VALIDATION_PATTERNS[strOption.validation_type]) {
        return {
          pattern: VALIDATION_PATTERNS[strOption.validation_type],
          message: `${t('common.inputMsg')}${t(`Model.${strOption.validation_type}`)}`,
        };
      }

      return null;
    };

    // 生成数字范围验证规则
    const getNumberRangeRule = (item: FullInfoAttrItem) => {
      const intOption = item.option as IntAttrOption;
      const hasMin =
        intOption?.min_value !== undefined &&
        intOption?.min_value !== '' &&
        intOption?.min_value !== null;
      const hasMax =
        intOption?.max_value !== undefined &&
        intOption?.max_value !== '' &&
        intOption?.max_value !== null;

      if (!hasMin && !hasMax) return null;

      return {
        validator: (_: any, value: any) => {
          if (value === undefined || value === null || value === '') {
            return Promise.resolve();
          }
          const numValue = Number(value);

          if (hasMin && numValue < Number(intOption.min_value)) {
            return Promise.reject(
              new Error(`${t('Model.min')}: ${intOption.min_value}`),
            );
          }

          if (hasMax && numValue > Number(intOption.max_value)) {
            return Promise.reject(
              new Error(`${t('Model.max')}: ${intOption.max_value}`),
            );
          }

          return Promise.resolve();
        },
      };
    };

    // 生成字段验证规则
    const getFieldRules = (item: FullInfoAttrItem) => {
      const rules: any[] = [
        {
          required: item.is_required && type !== 'batchEdit',
          message: t('required'),
        },
      ];

      // 字符串类型验证
      if (item.attr_type === 'str') {
        const stringRule = getStringValidationRule(item);
        if (stringRule) rules.push(stringRule);
      }

      // 数字类型范围验证
      if (item.attr_type === 'int') {
        const numberRule = getNumberRangeRule(item);
        if (numberRule) rules.push(numberRule);
      }

      return rules;
    };

    const renderFormField = (item: FullInfoAttrItem) => {
      const fieldDisabled =
        type === 'batchEdit'
          ? !enabledFields[item.attr_id]
          : !item.editable && type !== 'add';

      const hostDisabled = modelId === 'host' && item.attr_id === 'inst_name';

      const formField = (() => {
        // 特殊处理-主机的云区域为下拉选项（弹窗中）
        if (item.attr_id === 'cloud') {
          return (
            <Select
              disabled={fieldDisabled}
              placeholder={t('common.selectTip')}
            >
              {proxyOptions.map((opt) => {
                // 确保proxy_id是字符串格式
                return (
                  <Select.Option
                    key={String(opt.proxy_id)}
                    value={String(opt.proxy_id)}
                  >
                    {opt.proxy_name}
                  </Select.Option>
                );
              })}
            </Select>
          );
        }

        // 特殊处理-主机的云区域ID显示,但是不允许修改（弹窗中）
        if (item.attr_id === 'cloud_id' && modelId === 'host') {
          return <Input disabled={true} placeholder={t('common.inputTip')} />;
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
                {(Array.isArray(item.option) ? item.option : []).map((opt: any) => (
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
            const timeOption = item.option as TimeAttrOption;
            const displayFormat = timeOption?.display_format || 'datetime';
            const showTime = displayFormat === 'datetime';
            const format =
              displayFormat === 'datetime'
                ? 'YYYY-MM-DD HH:mm:ss'
                : 'YYYY-MM-DD';
            return (
              <DatePicker
                placeholder={t('common.selectTip')}
                showTime={showTime}
                disabled={fieldDisabled}
                format={format}
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
            if (item.attr_type === 'str') {
              const strOption = item.option as StrAttrOption;
              if (strOption?.widget_type === 'multi_line') {
                return (
                  <Input.TextArea
                    rows={4}
                    placeholder={t('common.inputTip')}
                    disabled={fieldDisabled || hostDisabled}
                  />
                );
              }
            }
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
            const target = allAttrs.find(
              (item: FullInfoAttrItem) => item.attr_id === key,
            );
            if (target?.attr_type === 'time' && values[key]) {
              const timeOpt = target.option as TimeAttrOption;
              const displayFmt = timeOpt?.display_format || 'datetime';
              if (displayFmt === 'date') {
                values[key] = values[key].format('YYYY-MM-DD') + ' 00:00:00';
              } else {
                values[key] = values[key].format('YYYY-MM-DD HH:mm:ss');
              }
            }
          }

          if (values.cloud) {
            values.cloud = String(values.cloud);
          }
          if (values.cloud_id) {
            values.cloud_id = +values.cloud_id;
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
            (enabled) => enabled,
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
          type === 'add' ? 'successfullyAdded' : 'successfullyModified',
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
          <Form form={form} layout="vertical">
            {(() => {
              const organizationAttrs = formItems.flatMap((group) =>
                (group.attrs || []).filter(
                  (attr) => attr.attr_id === 'organization',
                ),
              );

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
                          rules={getFieldRules(item)}
                        >
                          {renderFormField(item)}
                        </Form.Item>
                      </Col>
                    ))}
                  </Row>
                </>
              );
            })()}

            {formItems.map((group) => {
              const otherAttrs = (group.attrs || []).filter(
                (attr) => attr.attr_id !== 'organization',
              );
              if (otherAttrs.length === 0) return null;

              return (
                <div key={group.id}>
                  <div className={styles.groupOther}>{group.group_name}</div>
                  <Row gutter={24}>
                    {otherAttrs.map((item) => (
                      <Col span={12} key={item.attr_id}>
                        <Form.Item
                          className="mb-4"
                          name={item.attr_id}
                          label={renderFormLabel(item)}
                          rules={getFieldRules(item)}
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
