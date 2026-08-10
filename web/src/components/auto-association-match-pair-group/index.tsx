import type { ReactNode } from 'react';
import { Space, Tag } from 'antd';

export interface AutoAssociationMatchPairItem {
  key: string;
  label: ReactNode;
}

export interface AutoAssociationMatchPairGroupProps {
  items: AutoAssociationMatchPairItem[];
  emptyLabel?: ReactNode;
}

const AutoAssociationMatchPairGroup = ({
  items,
  emptyLabel = '--',
}: AutoAssociationMatchPairGroupProps) => {
  if (!items.length) {
    return <>{emptyLabel}</>;
  }

  return (
    <Space wrap size={[8, 8]}>
      {items.map((item) => (
        <Tag key={item.key}>{item.label}</Tag>
      ))}
    </Space>
  );
};

export default AutoAssociationMatchPairGroup;
