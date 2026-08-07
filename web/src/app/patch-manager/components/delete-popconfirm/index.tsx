'use client';

import React from 'react';
import { Popconfirm } from 'antd';
import type { PopconfirmProps } from 'antd';

const DELETE_POPOVER_STYLES: NonNullable<PopconfirmProps['styles']> = {
  root: {
    maxWidth: 500,
  },
  body: {
    maxWidth: 500,
    whiteSpace: 'normal',
    overflowWrap: 'anywhere',
  },
};

export default function PatchDeletePopconfirm({ styles, ...props }: PopconfirmProps) {
  return (
    <Popconfirm
      {...props}
      styles={{
        root: { ...DELETE_POPOVER_STYLES.root, ...styles?.root },
        body: { ...DELETE_POPOVER_STYLES.body, ...styles?.body },
      }}
    />
  );
}
