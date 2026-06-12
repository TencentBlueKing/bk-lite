'use client';

import React from 'react';
import type { FormInstance } from 'antd';
import type { ColumnItem } from '@/types';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

export interface AttributeEnterpriseFormContext {
  formRef: React.RefObject<FormInstance | null>;
  ui: {
    Form: any;
    Radio: any;
    Select: any;
  };
}

export interface AttributeEnterpriseColumnContext {
  ui: {
    Tag: any;
  };
}

export interface AttributeEnterpriseExtension {
  getInitialValues: (attrInfo: Partial<AttrFieldType>) => Record<string, unknown>;
  normalizeSubmitParams: (
    params: Record<string, unknown>,
    values: Record<string, unknown>
  ) => Record<string, unknown>;
  renderFormItems: (context: AttributeEnterpriseFormContext) => React.ReactNode;
  extendColumns: (columns: ColumnItem[], context: AttributeEnterpriseColumnContext) => ColumnItem[];
}

export function useCEAttributeEnterpriseExtension(): AttributeEnterpriseExtension {
  return React.useMemo(() => ({
    getInitialValues: () => ({}),
    normalizeSubmitParams: (params) => params,
    renderFormItems: () => null,
    extendColumns: (columns) => columns,
  }), []);
}

export function loadAttributeEnterpriseExtension() {
  try {
    // EE 增强判断：优先加载 enterprise hook，缺失时回退到 CE 默认实现。
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/app/cmdb/(enterprise)/hooks/useAttributeEnterpriseExtension');
    return mod.useAttributeEnterpriseExtension || useCEAttributeEnterpriseExtension;
  } catch {
    return useCEAttributeEnterpriseExtension;
  }
}
