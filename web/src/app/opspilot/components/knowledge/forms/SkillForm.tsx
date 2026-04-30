'use client';

import React, { useEffect, useState } from 'react';
import { Form, Input, Select } from 'antd';
import type { StaticImageData } from 'next/image';
import { Image } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';
import LatsAgent from '@/app/opspilot/img/lats_agent.png';
import PlanAgent from '@/app/opspilot/img/plan_agent.png';
import RagAgent from '@/app/opspilot/img/rag_agent.png';
import ReActAgent from '@/app/opspilot/img/reAct_agent.png';

const { Option } = Select;

interface SkillFormProps {
  form: any;
  initialValues?: any;
  visible: boolean;
}

const SkillForm: React.FC<SkillFormProps> = ({ form, initialValues, visible }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const [selectedType, setSelectedType] = useState<number>(2);

  const typeOptions = [
    { key: 2, title: t('skill.form.qaType'), desc: t('skill.form.qaTypeDesc'), scene: t('skill.form.qaTypeScene'), img: RagAgent },
    { key: 1, title: t('skill.form.toolsType'), desc: t('skill.form.toolsTypeDesc'), scene: t('skill.form.toolsTypeScene'), img: ReActAgent },
    { key: 3, title: t('skill.form.planType'), desc: t('skill.form.planTypeDesc'), scene: t('skill.form.planTypeScene'), img: PlanAgent },
    { key: 4, title: t('skill.form.complexType'), desc: t('skill.form.complexTypeDesc'), scene: t('skill.form.complexTypeScene'), img: LatsAgent }
  ];

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      form.setFieldsValue(initialValues);
      if (initialValues.skill_type !== undefined) setSelectedType(initialValues.skill_type);
    } else {
      form.resetFields();
      form.setFieldsValue({ skill_type: typeOptions[0].key });
      setSelectedType(typeOptions[0].key);
    }
  }, [initialValues, visible]);

  const handleTypeSelection = (typeKey: number) => {
    setSelectedType(typeKey);
    form.setFieldsValue({ skill_type: typeKey });
  };

  const renderSelectedTypeDetails = () => {
    const details = typeOptions.find((type) => type.key === selectedType);
    if (!details) return null;
    return (
      <div className="flex items-center my-2 border p-2 rounded-md">
        <div className="flex-1 text-sm">
          <h3 className="font-semibold">{t('skill.form.explanation')}</h3>
          <p className="text-[var(--color-text-2)] mb-4">{details.desc}</p>
          <h3 className="font-semibold">{t('skill.form.scene')}</h3>
          <p className="text-[var(--color-text-2)] whitespace-pre-line">{details.scene && `${details.scene}`}</p>
        </div>
        <div className="ml-4 w-[340px] flex items-center justify-center">
          <Image
            src={(details.img as StaticImageData)?.src}
            alt="example"
            className="rounded-md max-w-full max-h-full object-contain"
          />
        </div>
      </div>
    );
  };

  return (
    <Form form={form} layout="vertical" name="skill_form">
      <Form.Item
        name="skill_type"
        label={t('skill.form.type')}
        initialValue={typeOptions[0].key}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.type')}!` }]}
      >
        <Select placeholder={`${t('common.selectMsg')}${t('skill.form.type')}`} onChange={handleTypeSelection}>
          {typeOptions.map((type) => (
            <Option key={type.key} value={type.key}>{type.title}</Option>
          ))}
        </Select>
      </Form.Item>
      {renderSelectedTypeDetails()}
      <Form.Item
        name="name"
        label={t('skill.form.name')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('skill.form.name')}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t('skill.form.name')}`} />
      </Form.Item>
      <Form.Item
        name="team"
        label={t('skill.form.group')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.group')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('skill.form.group')}`} />
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t('skill.form.introduction')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('skill.form.introduction')}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t('skill.form.introduction')}`} />
      </Form.Item>
    </Form>
  );
};

export default SkillForm;
