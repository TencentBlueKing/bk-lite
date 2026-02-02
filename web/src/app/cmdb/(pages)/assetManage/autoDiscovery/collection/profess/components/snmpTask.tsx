'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import styles from '../index.module.scss';
import { CaretRightOutlined } from '@ant-design/icons';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  SNMP_FORM_INITIAL_VALUES,
  createTaskValidationRules,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import { Form, Spin, Input, Select, Collapse, InputNumber } from 'antd';

interface SNMPTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const SNMPTask: React.FC<SNMPTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const [snmpVersion, setSnmpVersion] = useState('v2');
  const [securityLevel, setSecurityLevel] = useState('authNoPriv');
  const localeContext = useLocale();
  const { model_id: modelId } = modelItem;

  const {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    formatCycleValue,
    onFinish,
  } = useTaskForm({
    modelId,
    editId,
    initialValues: SNMP_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const baseData = formatTaskValues({
        values,
        baseRef,
        selectedNode,
        modelItem,
        modelId,
        formatCycleValue,
      });

      const collectType = baseRef.current?.collectionType;
      const ipRange = values.ipRange?.length ? values.ipRange : undefined;
      const selectedData = baseRef.current?.selectedData;

      let instanceData;
      if (collectType === 'ip') {
        instanceData = {
          ip_range: ipRange.join('-'),
          instances: [],
        };
      } else {
        instanceData = {
          ip_range: '',
          instances: selectedData || [],
        };
      }

      const version = values.version;

      const credential: any = {
        version,
        snmp_port: values.snmp_port,
      };

      if (
        version !== 'v3' &&
        values.community &&
        values.community !== PASSWORD_PLACEHOLDER
      ) {
        credential.community = values.community;
      }

      if (version === 'v3') {
        credential.level = values.level;
        credential.username = values.username;
        credential.integrity = values.integrity;

        if (values.authkey && values.authkey !== PASSWORD_PLACEHOLDER) {
          credential.authkey = values.authkey;
        }

        if (values.level === 'authPriv') {
          credential.privacy = values.privacy;
          if (values.privkey && values.privkey !== PASSWORD_PLACEHOLDER) {
            credential.privkey = values.privkey;
          }
        }
      }

      return {
        ...baseData,
        ...instanceData,
        credential,
      };
    },
  });

  const rules: any = React.useMemo(
    () => createTaskValidationRules({ t, form, taskType: 'snmp' as const }),
    [t, form]
  );

  useEffect(() => {
    const initForm = async () => {
      if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        setSnmpVersion(values.credential.version);
        setSecurityLevel(values.credential.level);
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }
        form.setFieldsValue({
          ipRange,
          ...values,
          ...values.credential,
          organization: values.team || [],
          accessPointId: values.access_point?.[0]?.id,
        });
      } else {
        form.setFieldsValue(SNMP_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId]);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={SNMP_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.chooseAsset')}`}
          timeoutProps={{
            min: 0,
            defaultValue: 600,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Collapse
            ghost
            defaultActiveKey={['credential']}
            expandIcon={({ isActive }) => (
              <CaretRightOutlined
                rotate={isActive ? 90 : 0}
                className="text-base"
              />
            )}
          >
            <Collapse.Panel
              header={
                <div className={styles.panelHeader}>
                  {t('Collection.credential')}
                </div>
              }
              key="credential"
            >
              <Form.Item
                label={t('Collection.SNMPTask.version')}
                name="version"
                rules={rules.snmpVersion}
                required
              >
                <Select value={snmpVersion} onChange={setSnmpVersion}>
                  <Select.Option value="v2">V2</Select.Option>
                  <Select.Option value="v2c">V2C</Select.Option>
                  <Select.Option value="v3">V3</Select.Option>
                </Select>
              </Form.Item>

              <Form.Item
                label={t('Collection.port')}
                name="snmp_port"
                rules={rules.port}
              >
                <InputNumber min={1} max={65535} className="w-32" />
              </Form.Item>

              {snmpVersion !== 'v3' && (
                <Form.Item
                  label={t('Collection.SNMPTask.communityString')}
                  name="community"
                  rules={rules.communityString}
                  required
                >
                  <Input.Password
                    placeholder={t('common.inputTip')}
                    onFocus={(e) => {
                      if (!editId) return;
                      const value = e.target.value;
                      if (value === PASSWORD_PLACEHOLDER) {
                        form.setFieldValue('community', '');
                      }
                    }}
                    onBlur={(e) => {
                      if (!editId) return;
                      const value = e.target.value;
                      if (!value || value.trim() === '') {
                        form.setFieldValue('community', PASSWORD_PLACEHOLDER);
                      }
                    }}
                  />
                </Form.Item>
              )}

              {snmpVersion === 'v3' && (
                <>
                  <Form.Item
                    label={t('Collection.SNMPTask.securityLevel')}
                    name="level"
                    rules={[{ required: true, message: t('common.selectTip') }]}
                    initialValue="authPriv"
                  >
                    <Select onChange={setSecurityLevel}>
                      <Select.Option value="authNoPriv">
                        认证不加密
                      </Select.Option>
                      <Select.Option value="authPriv">认证加密</Select.Option>
                    </Select>
                  </Form.Item>

                  <Form.Item
                    label={t('Collection.SNMPTask.userName')}
                    name="username"
                    rules={[{ required: true, message: t('common.inputTip') }]}
                  >
                    <Input placeholder={t('common.inputTip')} />
                  </Form.Item>

                  <Form.Item
                    label={t('Collection.SNMPTask.authPassword')}
                    name="authkey"
                    rules={[{ required: true, message: t('common.inputTip') }]}
                  >
                    <Input.Password
                      placeholder={t('common.inputTip')}
                      onFocus={(e) => {
                        if (!editId) return;
                        const value = e.target.value;
                        if (value === PASSWORD_PLACEHOLDER) {
                          form.setFieldValue('authkey', '');
                        }
                      }}
                      onBlur={(e) => {
                        if (!editId) return;
                        const value = e.target.value;
                        if (!value || value.trim() === '') {
                          form.setFieldValue('authkey', PASSWORD_PLACEHOLDER);
                        }
                      }}
                    />
                  </Form.Item>

                  <Form.Item
                    label={t('Collection.SNMPTask.hashAlgorithm')}
                    name="integrity"
                    rules={[{ required: true, message: t('common.selectTip') }]}
                  >
                    <Select>
                      <Select.Option value="sha">SHA</Select.Option>
                      <Select.Option value="md5">MD5</Select.Option>
                    </Select>
                  </Form.Item>

                  {securityLevel === 'authPriv' && (
                    <>
                      <Form.Item
                        label={t('Collection.SNMPTask.encryptAlgorithm')}
                        name="privacy"
                        rules={[
                          { required: true, message: t('common.selectTip') },
                        ]}
                        initialValue="aes"
                      >
                        <Select>
                          <Select.Option value="aes">AES</Select.Option>
                          <Select.Option value="des">DES</Select.Option>
                        </Select>
                      </Form.Item>

                      <Form.Item
                        label={t('Collection.SNMPTask.encryptKey')}
                        name="privkey"
                        rules={[
                          { required: true, message: t('common.inputTip') },
                        ]}
                      >
                        <Input.Password
                          placeholder={t('common.inputTip')}
                          onFocus={(e) => {
                            if (!editId) return;
                            const value = e.target.value;
                            if (value === PASSWORD_PLACEHOLDER) {
                              form.setFieldValue('privkey', '');
                            }
                          }}
                          onBlur={(e) => {
                            if (!editId) return;
                            const value = e.target.value;
                            if (!value || value.trim() === '') {
                              form.setFieldValue(
                                'privkey',
                                PASSWORD_PLACEHOLDER
                              );
                            }
                          }}
                        />
                      </Form.Item>
                    </>
                  )}
                </>
              )}
            </Collapse.Panel>
          </Collapse>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default SNMPTask;
