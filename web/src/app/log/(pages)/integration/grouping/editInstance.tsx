'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
} from 'react';
import { Button, Form, message, Input, Select } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useLogApi from '@/app/log/api/integration';
import { ModalRef, ListItem, ModalProps } from '@/app/log/types';
import { FilterItem, GroupInfo } from '@/app/log/types/integration';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { cloneDeep } from 'lodash';
const { Option } = Select;
import groupingStyle from './index.module.scss';
import {
  useConditionList,
  useTermList,
} from '@/app/log/hooks/integration/common/other';
import { v4 as uuidv4 } from 'uuid';

const EditInstance = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, fields }, ref) => {
    const { createLogStreams, updateLogStreams, updateDefaultLogStreams } =
      useLogApi();
    const { t } = useTranslation();
    const CONDITION_LIST = useConditionList();
    const TERM_LIST = useTermList();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [configForm, setConfigForm] = useState<GroupInfo>({});
    const [title, setTitle] = useState<string>('');
    const [modalType, setModalType] = useState<string>('');
    const [term, setTerm] = useState<string | null>(null);
    const [conditions, setConditions] = useState<FilterItem[]>([
      {
        field: null,
        op: null,
        value: '',
      },
    ]);

    const isAdd = useMemo(() => {
      return modalType === 'add';
    }, [modalType]);

    const isBuiltIn = useMemo(() => {
      return modalType === 'builtIn';
    }, [modalType]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form, type }) => {
        // 开启弹窗的交互
        setTitle(title);
        setModalType(type);
        setConfigForm(cloneDeep(form));
        setVisible(true);
        if (type !== 'add') {
          setTerm(form.rule?.mode || null);
          setConditions(form.rule?.conditions || []);
        }
      },
    }));

    useEffect(() => {
      if (visible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue({
          name: configForm.name,
          organizations: configForm.organizations || [],
          collect_type_id: configForm.collect_type,
        });
      }
    }, [visible, configForm]);

    const handleOperate = async (params: GroupInfo) => {
      try {
        setConfirmLoading(true);
        const request = isAdd
          ? createLogStreams
          : isBuiltIn
            ? updateDefaultLogStreams
            : updateLogStreams;
        const msg = isAdd
          ? t('common.successfullyAdded')
          : t('common.successfullyModified');
        await request(params);
        message.success(msg);
        handleCancel();
        onSuccess();
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const params = {
          ...values,
          rule: {
            mode: term,
            conditions,
          },
          id: isAdd ? uuidv4() : configForm.id,
        };
        handleOperate(params);
      });
    };

    const handleCancel = () => {
      setVisible(false);
      setConditions([
        {
          field: null,
          op: null,
          value: '',
        },
      ]);
      setTerm(null);
    };

    const handleLabelChange = (val: string, index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].field = val;
      setConditions(_conditions);
    };

    const handleConditionChange = (val: string, index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].op = val;
      setConditions(_conditions);
    };

    const handleValueChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].value = e.target.value;
      setConditions(_conditions);
    };

    const addConditionItem = () => {
      const _conditions = cloneDeep(conditions);
      _conditions.push({
        field: null,
        op: null,
        value: '',
      });
      setConditions(_conditions);
    };

    const deleteConditionItem = (index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions.splice(index, 1);
      setConditions(_conditions);
    };

    // 自定义验证条件列表
    const validateDimensions = async () => {
      if (!conditions.length || !term) {
        return Promise.reject(new Error(t('common.required')));
      }
      if (
        conditions.length &&
        conditions.some((item) => {
          return Object.values(item).some((tex) => !tex);
        })
      ) {
        return Promise.reject(
          new Error(t('log.integration.conditionValidate'))
        );
      }
      return Promise.resolve();
    };

    return (
      <div>
        <OperateModal
          width={600}
          title={title}
          visible={visible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form ref={formRef} name="basic" layout="vertical">
            {!isBuiltIn && (
              <>
                <Form.Item<GroupInfo>
                  label={t('common.name')}
                  name="name"
                  rules={[{ required: true, message: t('common.required') }]}
                >
                  <Input placeholder={t('common.name')} />
                </Form.Item>
                <Form.Item<GroupInfo>
                  label={t('log.integration.rule')}
                  name="rule"
                  rules={[{ required: true, validator: validateDimensions }]}
                >
                  <div className="flex items-center mb-[20px]">
                    <span>{t('log.integration.meetRule')}</span>
                    <Select
                      className="ml-[8px] flex-1"
                      placeholder={t('log.integration.rule')}
                      showSearch
                      value={term}
                      onChange={(val) => setTerm(val)}
                    >
                      {TERM_LIST.map((item: ListItem) => (
                        <Option value={item.id} key={item.id}>
                          {item.name}
                        </Option>
                      ))}
                    </Select>
                  </div>
                  <div className={groupingStyle.conditionItem}>
                    {conditions.length ? (
                      <ul className={groupingStyle.conditions}>
                        {conditions.map((conditionItem, index) => (
                          <li
                            className={`${groupingStyle.itemOption} ${groupingStyle.filter}`}
                            key={index}
                          >
                            <Select
                              style={{
                                width: '180px',
                              }}
                              placeholder={t('log.label')}
                              showSearch
                              value={conditionItem.field}
                              onChange={(val) => handleLabelChange(val, index)}
                            >
                              {fields.map((item: string) => (
                                <Option value={item} key={item}>
                                  {item}
                                </Option>
                              ))}
                            </Select>
                            <Select
                              style={{
                                width: '118px',
                              }}
                              placeholder={t('log.term')}
                              value={conditionItem.op}
                              onChange={(val) =>
                                handleConditionChange(val, index)
                              }
                            >
                              {CONDITION_LIST.map((item: ListItem) => (
                                <Option value={item.id} key={item.id}>
                                  {item.name}
                                </Option>
                              ))}
                            </Select>
                            <Input
                              style={{
                                width: '180px',
                              }}
                              placeholder={t('log.value')}
                              value={conditionItem.value}
                              onChange={(e) => handleValueChange(e, index)}
                            ></Input>
                            {!!index && (
                              <Button
                                icon={<CloseOutlined />}
                                onClick={() => deleteConditionItem(index)}
                              />
                            )}
                            <Button
                              icon={<PlusOutlined />}
                              onClick={addConditionItem}
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <Button
                        icon={<PlusOutlined />}
                        onClick={addConditionItem}
                      />
                    )}
                  </div>
                </Form.Item>
              </>
            )}
            <Form.Item<GroupInfo>
              label={t('log.group')}
              name="organizations"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <GroupTreeSelector placeholder={t('log.group')} />
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);

EditInstance.displayName = 'EditInstance';
export default EditInstance;
