'use client';

import React from 'react';
import { Form, InputNumber, Select, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  APPLICATION3D_PAGE_EFFECTS,
  APPLICATION3D_WALL_DWELL_MAX,
  APPLICATION3D_WALL_DWELL_MIN,
  APPLICATION3D_WALL_PAGE_SIZE_DEFAULT,
  APPLICATION3D_WALL_PAGE_SIZE_MAX,
  APPLICATION3D_WALL_PAGE_SIZE_MIN,
  type Application3DPageEffect,
} from '@/app/ops-analysis/utils/application3DWallConfig';
import { ConfigSectionTitle } from '../configTitles';
import { ChartRoleLabel } from './chartRoleLabel';

const EFFECT_LABEL_KEYS: Record<Application3DPageEffect, [string, string]> = {
  slide: ['dashboard.application3DEffectSlide', '横向滑入'],
  fade: ['dashboard.application3DEffectFade', '淡入淡出'],
  flip: ['dashboard.application3DEffectFlip', '卡片翻转'],
  cut: ['dashboard.application3DEffectCut', '直接切换'],
};

interface PageSizeInputControlProps {
  id?: string;
  value?: number;
  onChange?: (value: number) => void;
  disabled?: boolean;
}

const PageSizeInputControl: React.FC<PageSizeInputControlProps> = ({
  id,
  value,
  onChange,
  disabled,
}) => {
  const { t } = useTranslation();
  const currentValue = value ?? APPLICATION3D_WALL_PAGE_SIZE_DEFAULT;

  const presets = [
    { value: 16, label: t('dashboard.application3DTier16', '16 大卡') },
    { value: 24, label: t('dashboard.application3DTier24', '24 标配') },
    { value: 36, label: t('dashboard.application3DTier36', '36 高密') },
  ];

  return (
    <div id={id} className="flex flex-wrap items-center gap-2">
      <InputNumber
        min={APPLICATION3D_WALL_PAGE_SIZE_MIN}
        max={APPLICATION3D_WALL_PAGE_SIZE_MAX}
        precision={0}
        disabled={disabled}
        value={value ?? APPLICATION3D_WALL_PAGE_SIZE_DEFAULT}
        onChange={(val) => {
          if (typeof val === 'number') {
            onChange?.(val);
          }
        }}
        className="w-32"
        addonAfter={t('dashboard.application3DCountUnit', '个')}
      />
      <div className="flex items-center gap-1.5">
        {presets.map((preset) => {
          const isSelected = currentValue === preset.value;
          return (
            <button
              key={preset.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange?.(preset.value)}
              className={`px-2.5 py-1 text-xs rounded border transition-colors cursor-pointer ${
                isSelected
                  ? 'border-[var(--color-primary)] text-[var(--color-primary)] bg-[var(--color-primary-bg-active)] font-medium'
                  : 'border-[var(--color-border-2)] text-[var(--color-text-3)] hover:text-[var(--color-text-1)] hover:border-[var(--color-border-1)] bg-[var(--color-bg)]'
              } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export const Application3DWallFields = () => {
  const { t } = useTranslation();
  const alarmPagesEnabled = Form.useWatch([
    'application3DWall',
    'alarmPagesEnabled',
  ]);
  const autoPageEnabled = Form.useWatch([
    'application3DWall',
    'autoPageEnabled',
  ]);

  const effectOptions = APPLICATION3D_PAGE_EFFECTS.map((effect) => ({
    value: effect,
    label: t(EFFECT_LABEL_KEYS[effect][0], EFFECT_LABEL_KEYS[effect][1]),
  }));

  return (
    <section>
      <ConfigSectionTitle>
        {t('dashboard.application3DWallSection', '应用墙')}
      </ConfigSectionTitle>

      {/* 1. 每页应用数（保留 Tooltip：解释 1~16 大卡与 17~36 标准取景的镜头自适应规则） */}
      <Form.Item
        name={['application3DWall', 'pageSize']}
        label={
          <ChartRoleLabel
            text={t('dashboard.application3DPageSize', '每页应用数')}
            tip={t(
              'dashboard.application3DPageSizeTip',
              '支持 1～36（默认 24）。1～16 为近景大卡聚焦，17～36 为标准/高密展示',
            )}
          />
        }
      >
        <PageSizeInputControl />
      </Form.Item>

      {/* 2. 翻页特效（移除 Tooltip：选项直观无歧义，减少视觉噪点） */}
      <Form.Item
        name={['application3DWall', 'pageEffect']}
        label={t('dashboard.application3DPageEffect', '翻页特效')}
      >
        <Select className="w-72 max-w-full" options={effectOptions} />
      </Form.Item>

      {/* 3. 有告警的应用单独成页（保留 Tooltip：解释大屏聚焦异常的应用排页机制） */}
      <div className="mb-6">
        <div className="flex h-8 items-center justify-between">
          <ChartRoleLabel
            text={t(
              'dashboard.application3DAlarmPages',
              '有告警的应用单独成页',
            )}
            tip={t(
              'dashboard.application3DAlarmPagesTip',
              '存在告警的应用将优先在最前面单独排页，便于大屏值班聚焦异常',
            )}
          />
          <Form.Item
            name={['application3DWall', 'alarmPagesEnabled']}
            valuePropName="checked"
            noStyle
          >
            <Switch />
          </Form.Item>
        </div>

        {alarmPagesEnabled ? (
          <div className="mt-3.5 border-l-2 border-[var(--color-border-2)] pl-3.5 pt-0.5">
            <Form.Item
              name={['application3DWall', 'alarmPageSize']}
              label={t('dashboard.application3DAlarmPageSize', '告警页每页数量')}
              className="!mb-0"
            >
              <PageSizeInputControl />
            </Form.Item>
          </div>
        ) : null}
      </div>

      {/* 4. 自动翻页（移除 Tooltip：通用直白概念；子项“每页停留”自带单位亦无需重复解释） */}
      <div className="mb-6">
        <div className="flex h-8 items-center justify-between">
          <span className="text-[14px] text-[var(--color-text-1)]">
            {t('dashboard.application3DAutoPage', '自动翻页')}
          </span>
          <Form.Item
            name={['application3DWall', 'autoPageEnabled']}
            valuePropName="checked"
            noStyle
          >
            <Switch />
          </Form.Item>
        </div>

        {autoPageEnabled ? (
          <div className="mt-3.5 border-l-2 border-[var(--color-border-2)] pl-3.5 pt-0.5">
            <Form.Item
              name={['application3DWall', 'dwellSeconds']}
              label={t('dashboard.application3DDwell', '每页停留')}
              className="!mb-0"
            >
              <InputNumber
                min={APPLICATION3D_WALL_DWELL_MIN}
                max={APPLICATION3D_WALL_DWELL_MAX}
                precision={0}
                className="w-32"
                addonAfter={t('dashboard.application3DDwellUnit', '秒')}
              />
            </Form.Item>
          </div>
        ) : null}
      </div>
    </section>
  );
};
