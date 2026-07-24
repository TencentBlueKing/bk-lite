'use client';

import React from 'react';
import { Form, Input, Radio, Switch, Tag, Typography, type FormInstance } from 'antd';
import { ApartmentOutlined, GlobalOutlined } from '@ant-design/icons';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';
import styles from './networkWhitelistFormModal.module.scss';

const { Text } = Typography;

export type NetworkWhitelistEntryType = 'cidr' | 'domain';

export interface NetworkWhitelistFormValues {
  network?: string;
  domain_name?: string;
  remark?: string;
  enabled?: boolean;
}

interface NetworkWhitelistFormModalProps {
  open: boolean;
  editing: boolean;
  entryType: NetworkWhitelistEntryType;
  form: FormInstance<NetworkWhitelistFormValues>;
  saving?: boolean;
  onEntryTypeChange: (type: NetworkWhitelistEntryType) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

const NetworkWhitelistFormModal: React.FC<NetworkWhitelistFormModalProps> = ({
  open,
  editing,
  entryType,
  form,
  saving = false,
  onEntryTypeChange,
  onSubmit,
  onCancel,
}) => {
  const { t } = useTranslation();
  const isDomain = entryType === 'domain';

  return (
    <OperateFormModal
      open={open}
      width={520}
      title={
        <div className={styles.titleBlock}>
          <span className={styles.titleText}>
            {editing ? t('system.settings.networkWhitelist.edit') : t('system.settings.networkWhitelist.add')}
          </span>
          <Text className={styles.titleDescription}>
            {editing
              ? t('system.settings.networkWhitelist.editDescription')
              : t('system.settings.networkWhitelist.createDescription')}
          </Text>
        </div>
      }
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      confirmLoading={saving}
      cancelDisabled={saving}
      primaryFirst={false}
      onConfirm={onSubmit}
      onCancel={onCancel}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" className={styles.form}>
        {!editing && (
          <div className={styles.typeSection}>
            <Text strong className={styles.typeLabel}>
              {t('system.settings.networkWhitelist.entryType')}
            </Text>
            <Radio.Group
              className={styles.typeSelector}
              value={entryType}
              onChange={(event) => onEntryTypeChange(event.target.value as NetworkWhitelistEntryType)}
            >
              <Radio value="cidr">
                <span className={styles.typeOption}>
                  <ApartmentOutlined />
                  {t('system.settings.networkWhitelist.typeCidr')}
                </span>
              </Radio>
              <Radio value="domain">
                <span className={styles.typeOption}>
                  <GlobalOutlined />
                  {t('system.settings.networkWhitelist.typeDomain')}
                </span>
              </Radio>
            </Radio.Group>
            <Text type="secondary" className={styles.typeHint}>
              {t('system.settings.networkWhitelist.entryTypeHint')}
            </Text>
          </div>
        )}

        {isDomain ? (
          <Form.Item
            name="domain_name"
            label={t('system.settings.networkWhitelist.domainName')}
            extra={t('system.settings.networkWhitelist.domainHint')}
            rules={[{ required: true, message: t('system.settings.networkWhitelist.domainRequired') }]}
          >
            <Input
              prefix={<GlobalOutlined className={styles.inputIcon} />}
              placeholder={t('system.settings.networkWhitelist.domainNamePlaceholder')}
            />
          </Form.Item>
        ) : (
          <Form.Item
            name="network"
            label={t('system.settings.networkWhitelist.network')}
            extra={t('system.settings.networkWhitelist.cidrHint')}
            rules={[{ required: true, message: t('system.settings.networkWhitelist.networkRequired') }]}
          >
            <Input
              prefix={<ApartmentOutlined className={styles.inputIcon} />}
              placeholder={t('system.settings.networkWhitelist.networkPlaceholder')}
            />
          </Form.Item>
        )}

        <Form.Item
          name="remark"
          label={
            <span className={styles.remarkLabel}>
              {t('system.settings.networkWhitelist.remark')}
              <Tag bordered={false}>{t('system.settings.networkWhitelist.optional')}</Tag>
            </span>
          }
        >
          <Input.TextArea rows={3} placeholder={t('system.settings.networkWhitelist.remarkPlaceholder')} />
        </Form.Item>

        <Form.Item
          name="enabled"
          label={t('system.settings.networkWhitelist.enabled')}
          valuePropName="checked"
          className={styles.enabledField}
        >
          <Switch size="small" aria-label={t('system.settings.networkWhitelist.enabled')} />
        </Form.Item>
      </Form>
    </OperateFormModal>
  );
};

export default NetworkWhitelistFormModal;
