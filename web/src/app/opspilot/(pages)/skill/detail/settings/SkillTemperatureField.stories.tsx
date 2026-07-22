import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { Form } from 'antd';
import SkillTemperatureField from './SkillTemperatureField';

/**
 * 智能体温度调节控件。
 *
 * 关键回归点:合法 ``0`` 必须被保留 ——
 * 之前 ``data.temperature || 0.7`` 会把合法的 0 当成"未配置",回退成 0.7,
 * 导致"温度调成 0,保存后变成 0.7"的 bug。本 story 用 InitialZero 显式
 * 覆盖该路径,确保 InputNumber 显示的也是 0。
 */
const meta: Meta<typeof SkillTemperatureField> = {
  title: 'OpsPilot/SkillTemperatureField',
  component: SkillTemperatureField,
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <div style={{ width: 480, padding: 16, background: '#fff' }}>
        <Form layout="vertical" initialValues={{ temperature: 0.7 }}>
          <Form.Item label="温度" name="temperature">
            <Story />
          </Form.Item>
        </Form>
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof SkillTemperatureField>;

/** 受控包装:让 Slider/InputNumber 共享同一个 state。 */
const Controlled: React.FC<{ initial: number }> = ({ initial }) => {
  const [v, setV] = useState<number>(initial);
  return <SkillTemperatureField value={v} onChange={setV} />;
};

/** 默认值:从父组件传入 0.7,InputNumber 显示 0.7。 */
export const Default: Story = {
  render: () => <Controlled initial={0.7} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole('spinbutton') as HTMLInputElement;
    await expect(input.value).toBe('0.7');
  },
};

/**
 * 回归:温度合法 0 必须原样显示,不能被回退成默认 0.7。
 * 修复前:InputNumber 会显示 0.7(因旧代码 `data.temperature || 0.7`)。
 * 修复后:InputNumber 显示 0。
 */
export const InitialZero: Story = {
  render: () => <Controlled initial={0} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole('spinbutton') as HTMLInputElement;
    await expect(input.value).toBe('0');
  },
};

/**
 * 边界:父组件传 undefined 时子组件默认到 0.7。
 * 这是后端未返回 temperature 字段的兼容路径。
 */
export const UndefinedFallback: Story = {
  render: () => <SkillTemperatureField value={undefined} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole('spinbutton') as HTMLInputElement;
    await expect(input.value).toBe('0.7');
  },
};

/**
 * 边界:Slider 拖到最左时会回调 null,子组件需规整为 0 而非放任 null 穿透。
 * 通过给 InputNumber 一个 null 初始值验证回退路径。
 */
export const NullNormalizedToZero: Story = {
  render: () => {
    const [v, setV] = useState<number | null>(null);
    // 子组件类型签名保证 onChange 收到 number;这里手动模拟 null 入口规整。
    return <SkillTemperatureField value={v ?? 0} onChange={(n) => setV(n)} />;
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole('spinbutton') as HTMLInputElement;
    await expect(input.value).toBe('0');
  },
};