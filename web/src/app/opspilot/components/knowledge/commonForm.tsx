import React from 'react';
import SkillForm from '@/app/opspilot/components/knowledge/forms/SkillForm';
import KnowledgeForm from '@/app/opspilot/components/knowledge/forms/KnowledgeForm';
import StudioForm from '@/app/opspilot/components/knowledge/forms/StudioForm';

interface CommonFormProps {
  form: any;
  modelOptions?: any[];
  initialValues?: any;
  isTraining?: boolean;
  formType: string;
  visible: boolean;
}

/** @deprecated Use SkillForm / KnowledgeForm / StudioForm directly */
const CommonForm: React.FC<CommonFormProps> = (props) => {
  const { formType, ...rest } = props;
  if (formType === 'skill') return <SkillForm {...rest} />;
  if (formType === 'knowledge') return <KnowledgeForm {...rest} />;
  if (formType === 'studio') return <StudioForm {...rest} />;
  return null;
};

export default CommonForm;
