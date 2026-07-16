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
    <div className="flex items-start gap-4">
      {control}
      {description ? (
        <div className="flex-1 text-[var(--color-text-3)]">{description}</div>
      ) : null}
    </div>
  );
};

export default IntegrationSettingRow;
