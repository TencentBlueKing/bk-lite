import React from 'react';
import FieldGuideTip from '@/components/field-guide-tip';

const PersonFieldLabel: React.FC<{ label: string; tip: string }> = ({ label, tip }) => (
  <span className="inline-flex items-center">
    {label}
    <FieldGuideTip title={label} short={tip} />
  </span>
);

export default PersonFieldLabel;
