import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import Icon from '@/components/icon';

const { Option } = Select;

interface CommonFormProps {
  form: any;
  modelOptions?: any[];
  initialValues?: any;
  isTraining?: boolean;
  formType: string;
  visible: boolean;
}

const CommonForm: React.FC<CommonFormProps> = ({ form, modelOptions, initialValues, isTraining, formType, visible }) => {
  const { t } = useTranslation();
  const { groups, selectedGroup } = useUserInfoContext();

  const [selectedType, setSelectedType] = useState<number>(2);

  const typeOptions = [
    { 
      key: 2, 
      title: t('skill.form.qaType'), 
      desc: t('skill.form.qaTypeDesc'), 
      icon: 'liaotian' 
    },
    { 
      key: 1, 
      title: t('skill.form.toolsType'), 
      desc: t('skill.form.toolsTypeDesc'), 
      icon: 'gongju'
    },
  ];

  useEffect(() => {
    if (!visible) return;

    if (initialValues) {
      form.setFieldsValue(initialValues);
    } else {
      form.resetFields();
      const defaultValues: any = {};
      if (formType === 'knowledge' && modelOptions && modelOptions.length > 0) {
        defaultValues.embed_model = modelOptions[0].id;
      }
      form.setFieldsValue(defaultValues);
    }
  }, [initialValues, form, modelOptions, formType, visible]);

  const handleTypeSelection = (typeKey: number) => {
    setSelectedType(typeKey);
    form.setFieldsValue({ skill_type: typeKey });
  };

  return (
    <Form form={form} layout="vertical" name={`${formType}_form`}>
      {formType === 'skill' && (
        <Form.Item name="skill_type" initialValue={typeOptions[0].key}>
          <div className="grid grid-cols-2 gap-4">
            {typeOptions.map((type) => (
              <Tooltip key={type.key} title={type.desc}>
                <div
                  className={`p-4 rounded-lg cursor-pointer ${
                    selectedType === type.key ? 'border-2 bg-[var(--color-primary-bg-active)] border-[var(--color-primary)]' : 'border'
                  }`}
                  onClick={() => handleTypeSelection(type.key)}
                >
                  <div className="flex items-center mb-2">
                    <Icon type={type.icon} className="text-2xl mr-2" />
                    <h3 className="text-sm font-semibold">{type.title}</h3>
                  </div>
                  <p className="text-xs text-[var(--color-text-3)] line-clamp-3">{type.desc}</p>
                </div>
              </Tooltip>
            ))}
          </div>
        </Form.Item>
      )}
      <Form.Item
        name="name"
        label={t(`${formType}.form.name`)}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t(`${formType}.form.name`)}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t(`${formType}.form.name`)}`} />
      </Form.Item>
      {formType === 'knowledge' && modelOptions && (
        <Form.Item
          name="embed_model"
          label={t('knowledge.form.embedModel')}
          tooltip={t('knowledge.form.embedModelTip')}
          rules={[{ required: true, message: `${t('common.selectMsg')}${t('knowledge.form.embedModel')}!` }]}
        >
          <Select placeholder={`${t('common.selectMsg')}${t('knowledge.form.embedModel')}`} disabled={isTraining}>
            {modelOptions.map((model) => (
              <Option key={model.id} value={model.id} disabled={!model.enabled}>
                {model.name}
              </Option>
            ))}
          </Select>
        </Form.Item>
      )}
      <Form.Item
        name="team"
        label={t(`${formType}.form.group`)}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t(`${formType}.form.group`)}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <Select
          mode="multiple"
          placeholder={`${t('common.selectMsg')}${t(`${formType}.form.group`)}`}
        >
          {groups.map(group => (
            <Select.Option key={group.id} value={group.id}>
              {group.name}
            </Select.Option>
          ))}
        </Select>
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t(`${formType}.form.introduction`)}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t(`${formType}.form.introduction`)}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t(`${formType}.form.introduction`)}`} />
      </Form.Item>
    </Form>
  );
};

export default CommonForm;
