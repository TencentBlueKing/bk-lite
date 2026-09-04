import React from 'react';
import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleFilled,
  ClusterOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';

const DEVICE_TYPE_ICONS: Record<string, React.ReactNode> = {
  switch: <BranchesOutlined className="text-xl" />,
  router: <ApiOutlined className="text-xl" />,
  firewall: <SafetyCertificateOutlined className="text-xl" />,
  loadbalance: <ClusterOutlined className="text-xl" />,
};

interface DeviceTypeOption {
  key: string;
  label: string;
}

interface ScanDeviceTypePickerProps {
  options: DeviceTypeOption[];
  value?: string;
  onChange: (key: string) => void;
  compact?: boolean;
}

const ScanDeviceTypePicker: React.FC<ScanDeviceTypePickerProps> = ({ options, value, onChange, compact }) => (
  <div className={compact ? 'grid grid-cols-2 gap-2.5' : 'grid grid-cols-2 gap-3'}>
    {options.map((option) => {
      const isSelected = value === option.key;
      return (
        <button
          type="button"
          key={option.key}
          onClick={() => onChange(option.key)}
          className={`relative flex items-center text-left transition-all ${
            compact ? 'gap-2.5 rounded-lg border p-2.5' : 'gap-3 rounded-lg border p-3'
          } ${
            isSelected
              ? 'border-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_8%,transparent)] font-medium text-[var(--color-primary)]'
              : 'border-[var(--color-border-2)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)]'
          } ${isSelected && !compact ? 'shadow-sm' : ''}`}
        >
          <div className={isSelected ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}>
            {DEVICE_TYPE_ICONS[option.key] || <BranchesOutlined className="text-xl" />}
          </div>
          {compact ? (
            <span className="text-sm">{option.label}</span>
          ) : (
            <div className="flex flex-col">
              <span className="text-sm font-medium">{option.label}</span>
              <span className="text-[11px] text-[var(--color-text-4)] uppercase">{option.key}</span>
            </div>
          )}
          {isSelected ? (
            <CheckCircleFilled
              className={`absolute text-[var(--color-primary)] ${compact ? 'right-2 top-2 text-xs' : 'right-2.5 top-2.5 text-sm'}`}
            />
          ) : null}
        </button>
      );
    })}
  </div>
);

export default ScanDeviceTypePicker;
