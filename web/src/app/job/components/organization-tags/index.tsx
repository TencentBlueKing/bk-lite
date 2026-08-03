import React from 'react';
import { Tag } from 'antd';

export { getOrganizationColumnWidth } from './layout';

export interface OrganizationTagsProps {
  names?: string[] | null;
}

const OrganizationTags: React.FC<OrganizationTagsProps> = ({ names }) => {
  if (!names?.length) return <span>-</span>;

  return (
    <div className="flex flex-nowrap items-center gap-1 whitespace-nowrap">
      {names.map((name, index) => (
        <Tag
          key={`${name}-${index}`}
          className="whitespace-nowrap"
          style={{ marginInlineEnd: 0 }}
        >
          {name}
        </Tag>
      ))}
    </div>
  );
};

export default OrganizationTags;
