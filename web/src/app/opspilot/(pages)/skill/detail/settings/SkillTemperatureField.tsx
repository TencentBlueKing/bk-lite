'use client';

import React from 'react';
import { Slider, InputNumber } from 'antd';

export interface SkillTemperatureFieldProps {
  /** 当前温度值(0 - 1)。 */
  value?: number;
  /** 值变化回调,保证非 null(Slider 拖到最左的 null 在此处统一规整为 0)。 */
  onChange?: (value: number) => void;
}

/**
 * 智能体温度调节控件(Slider + InputNumber)。
 *
 * 重要约定 — 读取回显时不要用 ``||``,必须用 ``??``:
 *   - 合法的 ``0`` 必须保留,否则 ``temperature=0`` 保存后会回显成默认 ``0.7``
 *     (因为 ``0 || 0.7 === 0.7``)。
 *   - 父组件读取后端值时统一写成 ``data.temperature ?? 0.7``。
 *
 * 子组件内部把 Slider 拖到最左时回调的 ``null`` 规整为 ``0``,避免父组件
 * 重复处理 falsy 边界。
 */
const SkillTemperatureField: React.FC<SkillTemperatureFieldProps> = ({ value = 0.7, onChange }) => {
  const handleChange = (next: number | null) => {
    onChange?.(next === null ? 0 : next);
  };

  return (
    <div className="flex gap-4" data-testid="skill-temperature-field">
      <Slider
        className="flex-1"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={handleChange}
      />
      <InputNumber
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={handleChange}
      />
    </div>
  );
};

export default SkillTemperatureField;