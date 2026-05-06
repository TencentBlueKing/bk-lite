import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';

interface BaseEntityFieldsProps {
  formType: string;
}

const BaseEntityFields: React.FC<BaseEntityFieldsProps> = ({ formType }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();

  return (
    <>
      <Form.Item
        name="name"
        label={t(`${formType}.form.name`)}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t(`${formType}.form.name`)}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t(`${formType}.form.name`)}`} />
      </Form.Item>
      <Form.Item
        name="team"
        label={t(`${formType}.form.group`)}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t(`${formType}.form.group`)}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect
          placeholder={`${t('common.selectMsg')}${t(`${formType}.form.group`)}`}
        />
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t(`${formType}.form.introduction`)}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t(`${formType}.form.introduction`)}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t(`${formType}.form.introduction`)}`} />
      </Form.Item>
    </>
  );
};

export default BaseEntityFields;
