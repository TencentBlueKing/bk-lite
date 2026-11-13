'use client';

import React, { useEffect, useRef, useState } from 'react';
import type { OrderFieldOption } from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import OrderInput from '@/app/ops-analysis/components/orderInput';
import { loadConditionModelFields } from '@/app/ops-analysis/components/conditionFilterControl';
import { parseOrderValue } from '@/app/ops-analysis/utils/orderValue';

interface OrderControlProps {
  value?: unknown;
  onChange?: (value: string) => void;
  fields: OrderFieldOption[];
  modelParam?: string;
  includeModelAttrsInModes?: string[];
  formParams?: Record<string, unknown>;
  analysisMode?: string;
  queryObject?: string;
  disabled?: boolean;
}

const OrderControl: React.FC<OrderControlProps> = ({
  value,
  onChange,
  fields,
  modelParam,
  includeModelAttrsInModes,
  formParams,
  analysisMode,
  queryObject = '',
  disabled = false,
}) => {
  const api = useDataSourceApi();
  // 这个 hook 每次渲染都返回新对象。放进依赖后，属性加载的 setState 会立刻再发一次请求。
  const apiRef = useRef(api);
  apiRef.current = api;
  const [modelFields, setModelFields] = useState<OrderFieldOption[]>([]);
  const [attrsReady, setAttrsReady] = useState(false);
  const modelId = modelParam ? String(formParams?.[modelParam] ?? '') : '';
  const visible = fields.filter((field) => {
    if (field.modes?.length && analysisMode && !field.modes.includes(analysisMode)) return false;
    if (field.query_objects?.length && queryObject && !field.query_objects.includes(queryObject)) return false;
    return true;
  });
  const visibleKey = visible.map((field) => field.value).join('\0');
  const modelAttrModesKey = (includeModelAttrsInModes ?? []).join('\0');

  useEffect(() => {
    const modes = modelAttrModesKey ? modelAttrModesKey.split('\0') : [];
    const shouldLoad = Boolean(
      modelParam
      && modelId
      && (!modes.length || (analysisMode && modes.includes(analysisMode))),
    );
    if (!shouldLoad) {
      // 空数组每次都是新引用。表单参数对象每轮渲染都会换，直接 setState 会把配置抽屉打成死循环。
      setModelFields((current) => (current.length ? [] : current));
      setAttrsReady(true);
      return undefined;
    }
    setAttrsReady(false);
    let cancelled = false;
    void loadConditionModelFields(apiRef.current, modelId).then((loaded) => {
      if (!cancelled) {
        setModelFields(loaded.map((field) => ({ value: field.value, label: field.label })));
        setAttrsReady(true);
      }
    }).catch(() => {
      if (!cancelled) {
        setModelFields((current) => (current.length ? [] : current));
        setAttrsReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [analysisMode, modelAttrModesKey, modelId, modelParam]);

  const modelFieldKey = modelFields.map((field) => field.value).join('\0');
  useEffect(() => {
    if (!attrsReady || !onChange) return;
    const current = parseOrderValue(value).field;
    if (!current) return;
    const allowed = new Set(`${visibleKey}\0${modelFieldKey}`.split('\0').filter(Boolean));
    if (!allowed.has(current)) onChange('');
  }, [attrsReady, modelFieldKey, onChange, value, visibleKey]);

  const merged = [...visible];
  modelFields.forEach((field) => {
    if (!merged.some((item) => item.value === field.value)) merged.push(field);
  });

  return (
    <OrderInput
      value={value}
      onChange={onChange}
      fields={merged}
      disabled={disabled}
    />
  );
};

export default OrderControl;
