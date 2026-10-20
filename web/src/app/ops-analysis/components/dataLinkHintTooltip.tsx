import React from 'react';
import { Tooltip } from 'antd';

/** 有数据链接提示时包一层 Tooltip；没有时原样返回，不影响未配链接的组件。 */
const DataLinkHintTooltip: React.FC<{
  hint?: React.ReactNode;
  children: React.ReactElement;
}> = ({ hint, children }) => (
  hint ? (
    <Tooltip title={hint} mouseEnterDelay={0}>
      {children}
    </Tooltip>
  ) : children
);

export default DataLinkHintTooltip;
