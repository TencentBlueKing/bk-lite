import React, { useEffect, useMemo } from 'react';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { Form, Input, Segmented, Tooltip } from 'antd';

import { FilterTokenInput } from '@/app/ops-analysis/components/filterTokenInput';
import type {
  UnifiedFilterDefinition,
  ValueConfig,
  WidgetInteractionKind,
} from '@/app/ops-analysis/types/dashBoard';
import { buildInteractionPoints } from '@/app/ops-analysis/utils/interactionPoints';
import {
  interactionCapability,
  isAllowedInteractionUrl,
  listInteractionVariables,
  listPresentDataVariables,
} from '@/app/ops-analysis/utils/interactionLink';

type Translate = (
  key: string,
  defaultValue?: string,
  values?: Record<string, string | number>,
) => string;

type InteractionChoice = 'none' | WidgetInteractionKind;

interface InteractionLinkSectionProps {
  t: Translate;
  chartType?: string;
  definitions: UnifiedFilterDefinition[];
  rawData: unknown;
  fieldConfig?: ValueConfig | null;
  /** 大屏无边框没有标题，标题链接不可新选，已有配置保留。 */
  titleLinkUnavailable?: boolean;
  /** 大屏文本项：图标跟在文本后，不提供数据链接。 */
  besideText?: boolean;
  /** 选「无」时清掉名称、URL 和打开方式，避免切回标题链接后又出现。 */
  clearOnNone?: boolean;
  /** setFieldsValue 不会触发 Form.onValuesChange，种类切换后补一次。 */
  onDraftChange?: () => void;
}

const InteractionLinkSection: React.FC<InteractionLinkSectionProps> = ({
  t,
  chartType,
  definitions,
  rawData,
  fieldConfig,
  titleLinkUnavailable = false,
  besideText = false,
  clearOnNone = false,
  onDraftChange,
}) => {
  const form = Form.useFormInstance();
  const watchedKind = Form.useWatch(['interaction', 'kind'], form) as InteractionChoice | undefined;
  const kind = watchedKind ?? (form.getFieldValue(['interaction', 'kind']) as InteractionChoice | undefined);
  const capability = besideText
    ? { title: true, data: false as const }
    : interactionCapability(chartType);
  const selectedKind: InteractionChoice = kind === 'data'
    ? (capability.data ? 'data' : 'title')
    : kind === 'title'
      ? 'title'
      : 'none';

  useEffect(() => {
    if (capability.data || kind !== 'data') return;
    form.setFieldValue(['interaction', 'kind'], 'title');
  }, [capability.data, form, kind]);

  const variables = useMemo(() => {
    const points = buildInteractionPoints(chartType, rawData, fieldConfig);
    const dataVariables = listPresentDataVariables(chartType, rawData, {
      valueGroup: t('dashboard.interactionGroupValue', '数据点'),
      fieldGroup: t('dashboard.interactionGroupField', '数据字段'),
      fieldLabel: (field) => field,
      category: t('dashboard.interactionPointCategory', '分类'),
      series: t('dashboard.interactionSeriesName', '系列'),
      name: t('dashboard.interactionPointName', '名称'),
      indicator: t('dashboard.interactionPointIndicator', '指标'),
      time: t('dashboard.interactionValueTime', '时间'),
      numeric: t('dashboard.interactionValueNumeric', '数值'),
      cabinetGroup: t('dashboard.interactionGroupCabinet', '机柜'),
      cabinetId: t('dashboard.interactionCabinetId', '机柜 ID'),
      cabinetName: t('dashboard.interactionCabinetName', '机柜名称'),
      cabinetLocation: t('dashboard.interactionCabinetLocation', '机柜位置'),
      cabinetType: t('dashboard.interactionCabinetType', '机柜类型'),
      cabinetState: t('dashboard.interactionCabinetState', '机柜状态'),
      deviceGroup: t('dashboard.interactionGroupDevice', '设备'),
      deviceId: t('dashboard.interactionDeviceId', '设备 ID'),
      deviceName: t('dashboard.interactionDeviceName', '设备名称'),
      deviceModel: t('dashboard.interactionModelId', '模型 ID'),
      deviceUStart: t('dashboard.interactionDeviceUStart', '起始 U 位'),
      systemGroup: t('dashboard.interactionGroupSystem', '应用系统'),
      systemId: t('dashboard.interactionSystemId', '系统 ID'),
      systemName: t('dashboard.interactionSystemName', '系统名称'),
      hostGroup: t('dashboard.interactionGroupHost', '主机'),
      hostId: t('dashboard.interactionHostId', '主机 ID'),
      hostName: t('dashboard.interactionHostName', '主机名称'),
      hostIp: t('dashboard.interactionHostIp', '主机 IP'),
      hostOs: t('dashboard.interactionHostOs', '操作系统'),
      applicationGroup: t('dashboard.interactionGroupApplication', '应用'),
      applicationId: t('dashboard.interactionApplicationId', '应用 ID'),
      applicationName: t('dashboard.interactionApplicationName', '应用名称'),
      objectGroup: t('dashboard.interactionGroupObject', '对象'),
      objectType: t('dashboard.interactionObjectType', '对象类型'),
      objectId: t('dashboard.interactionObjectId', '对象 ID'),
      objectName: t('dashboard.interactionObjectName', '对象名称'),
      objectModelId: t('dashboard.interactionObjectModelId', '对象模型 ID'),
    }, points);
    return listInteractionVariables({
      definitions,
      dataVariables: selectedKind === 'data' ? dataVariables : [],
      filterGroup: t('dashboard.interactionGroupFilter', '画布筛选'),
      timeStartLabel: (name) => t('dashboard.interactionTimeStart', '{name} 开始', { name }),
      timeEndLabel: (name) => t('dashboard.interactionTimeEnd', '{name} 结束', { name }),
    });
  }, [chartType, definitions, fieldConfig, rawData, selectedKind, t]);

  const selectKind = (next: InteractionChoice) => {
    if (next === 'title' && titleLinkUnavailable) return;
    if (next === 'data' && !capability.data) return;
    if (next === 'none' && clearOnNone) {
      form.setFieldsValue({
        interaction: { kind: 'none', name: '', url: '', openMode: 'sameTab' },
      });
      onDraftChange?.();
      return;
    }
    form.setFieldValue(['interaction', 'kind'], next);
    onDraftChange?.();
  };

  const linkTypeTip = (
    <div>
      <div>{t('dashboard.interactionNoneTip', '无：不设置跳转')}</div>
      {besideText ? (
        <div>{t('dashboard.interactionTextTitleTip', '标题链接：文本行最右侧显示 > 图标')}</div>
      ) : capability.data ? (
        <>
          <div>{t('dashboard.interactionLinkTypeTitleTip', '标题链接：标题行最右侧显示 > 图标')}</div>
          <div>{t('dashboard.interactionLinkTypeDataTip', '数据链接：点击数据点、柱、扇区或数字打开')}</div>
        </>
      ) : (
        <div>{t('dashboard.interactionTitleOnlyTip', '该组件仅支持标题链接，点击标题行最右侧 > 打开')}</div>
      )}
    </div>
  );

  return (
    <section>
      <Form.Item name={['interaction', 'kind']} hidden>
        <Input />
      </Form.Item>
      <div className="space-y-4">
        <div>
          <div className="mb-2 flex items-center text-sm text-(--color-text-1)">
            <span>{t('dashboard.interactionLinkType', '链接类型')}</span>
            <Tooltip title={linkTypeTip}>
              <QuestionCircleOutlined className="ml-1 cursor-help text-(--color-text-3)" />
            </Tooltip>
          </div>
          <Segmented
            value={selectedKind}
            onChange={(value) => {
              if (value === 'none' || value === 'title' || value === 'data') selectKind(value);
            }}
            options={[
              { label: t('dashboard.interactionNone', '无'), value: 'none' },
              {
                label: titleLinkUnavailable ? (
                  <Tooltip title={t('dashboard.interactionTitleLinkBareDisabled', '无边框样式不显示标题，无法使用标题链接')}>
                    <span>{t('dashboard.interactionTitleLink', '标题链接')}</span>
                  </Tooltip>
                ) : t('dashboard.interactionTitleLink', '标题链接'),
                value: 'title',
                disabled: titleLinkUnavailable,
              },
              ...(capability.data
                ? [{ label: t('dashboard.interactionDataLink', '数据链接'), value: 'data' }]
                : []),
            ]}
          />
          {selectedKind === 'title' && titleLinkUnavailable ? (
            <p className="mb-0 mt-2 text-xs text-(--color-warning)">
              {t('dashboard.interactionTitleLinkBareWarning', '当前为无边框样式，标题链接不会显示，切换为标准样式后生效')}
            </p>
          ) : null}
        </div>
        {selectedKind === 'none' ? (
          <p className="mb-0 text-xs text-(--color-text-3)">
            {t('dashboard.interactionNoneHint', '未设置交互，组件不可点击跳转')}
          </p>
        ) : (
          <>
            <Form.Item
              label={t('dashboard.interactionName', '名称')}
              name={['interaction', 'name']}
              preserve
            >
              <Input placeholder={t('dashboard.interactionNamePlaceholder', '例如：查看详情')} />
            </Form.Item>
            <Form.Item
              label={t('dashboard.interactionUrl', '目标 URL')}
              name={['interaction', 'url']}
              required
              preserve
              rules={[{
                validator: async (_, value: unknown) => {
                  if (typeof value !== 'string' || !value.trim()) {
                    throw new Error(t('dashboard.interactionUrlRequired', '请输入 URL'));
                  }
                  if (!isAllowedInteractionUrl(value)) {
                    throw new Error(t('dashboard.interactionUrlBlocked', '链接协议不被允许'));
                  }
                },
              }]}
            >
              <FilterTokenInput
                t={t}
                variables={variables}
                hint=""
                allowClear
                placeholder={t('dashboard.interactionUrlPlaceholder', '输入 URL，键入 $ 插入变量')}
              />
            </Form.Item>
            <Form.Item
              label={t('dashboard.interactionOpenMode', '打开方式')}
              name={['interaction', 'openMode']}
              preserve
            >
              <Segmented
                size="small"
                options={[
                  { label: t('dashboard.interactionSameTab', '当前页'), value: 'sameTab' },
                  { label: t('dashboard.interactionNewTab', '新标签'), value: 'newTab' },
                ]}
              />
            </Form.Item>
          </>
        )}
      </div>
    </section>
  );
};

export default InteractionLinkSection;
