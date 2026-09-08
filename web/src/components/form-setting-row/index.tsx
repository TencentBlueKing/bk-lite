import React from 'react';

interface IntegrationSettingRowProps {
  control: React.ReactNode;
  description?: React.ReactNode;
}

const IntegrationSettingRow: React.FC<IntegrationSettingRowProps> = ({
  control,
  description,
}) => {
  return (
    <div className="flex flex-col items-start gap-1">
      {control}
      {description ? (
        <div className="w-full text-[var(--color-text-3)] leading-5">{description}</div>
      ) : null}
    </div>
  );
};

export default IntegrationSettingRow;
