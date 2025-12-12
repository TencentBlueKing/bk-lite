import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Image } from 'antd';
import type { StaticImageData } from 'next/image';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';
import LatsAgent from '@/app/opspilot/img/lats_agent.png';
import PlanAgent from '@/app/opspilot/img/plan_agent.png';
import RagAgent from '@/app/opspilot/img/rag_agent.png';
import ReActAgent from '@/app/opspilot/img/reAct_agent.png';

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
  const { selectedGroup } = useUserInfoContext();

  const [selectedType, setSelectedType] = useState<number>(2);

  const typeOptions = [
    { 
      key: 2, 
      title: t('skill.form.qaType'), 
      desc: t('skill.form.qaTypeDesc'), 
      scene: t('skill.form.qaTypeScene'),
      img: RagAgent
    },
    { 
      key: 1, 
      title: t('skill.form.toolsType'), 
      desc: t('skill.form.toolsTypeDesc'), 
      scene: t('skill.form.toolsTypeScene'),
      img: ReActAgent
    },
    { 
      key: 3, 
      title: t('skill.form.planType'), 
      desc: t('skill.form.planTypeDesc'),
      scene: t('skill.form.planTypeScene'), 
      img: PlanAgent
    },
    { 
      key: 4, 
      title: t('skill.form.complexType'), 
      desc: t('skill.form.complexTypeDesc'), 
      scene: t('skill.form.complexTypeScene'),
      img: LatsAgent
    }
  ];

  useEffect(() => {
    if (!visible) return;

    if (initialValues) {
      form.setFieldsValue(initialValues);
      if (initialValues.skill_type !== undefined) {
        setSelectedType(initialValues.skill_type);
      }
    } else {
      form.resetFields();
      const defaultValues: any = {};
      if (formType === 'knowledge' && modelOptions && modelOptions.length > 0) {
        defaultValues.embed_model = modelOptions[0].id;
      }
      if (formType === 'skill') {
        defaultValues.skill_type = typeOptions[0].key;
        setSelectedType(typeOptions[0].key);
      }
      if (formType === 'studio') {
        defaultValues.bot_type = 3;
      }
      form.setFieldsValue(defaultValues);
    }
  }, [initialValues, visible]);

  const handleTypeSelection = (typeKey: number) => {
    setSelectedType(typeKey);
    form.setFieldsValue({ skill_type: typeKey });
  };

  const renderSelectedTypeDetails = () => {
    const selectedTypeDetails = typeOptions.find((type) => type.key === selectedType);
    if (!selectedTypeDetails) return null;

    const { desc, scene, img } = selectedTypeDetails;

    return (
      <div className="flex items-center my-2 border p-2 rounded-md">
        <div className="flex-1">
          <div className="text-sm">
            <h3 className='font-semibold'>{t('skill.form.explanation')}</h3>
            <p className='text-[var(--color-text-2)] mb-4'>{desc}</p>
            <h3 className='font-semibold'>{t('skill.form.scene')}</h3>
            <p className='text-[var(--color-text-2)] whitespace-pre-line'>{scene && `${scene}`}</p>
          </div>
        </div>
        <div className="ml-4 w-[340px] flex items-center justify-center">
          <Image
            src={(img as StaticImageData)?.src}
            alt="example"
            className="rounded-md max-w-full max-h-full object-contain"
          />
        </div> 
      </div>
    );
  };

  return (
    <Form form={form} layout="vertical" name={`${formType}_form`}>
      {formType === 'skill' && (
        <Form.Item
          name="skill_type"
          label={t('skill.form.type')}
          initialValue={typeOptions[0].key}
          rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.type')}!` }]}
        >
          <Select
            placeholder={`${t('common.selectMsg')}${t('skill.form.type')}`}
            onChange={handleTypeSelection}
          >
            {typeOptions.map((type) => (
              <Option key={type.key} value={type.key}>
                {type.title}
              </Option>
            ))}
          </Select>
        </Form.Item>
      )}
      {formType === 'skill' && renderSelectedTypeDetails()}
      
      {formType === 'studio' && (
        <Form.Item
          name="bot_type"
          hidden
          initialValue={3}
        >
          <Input type="hidden" />
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
    </Form>
  );
};

export default CommonForm;
