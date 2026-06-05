'use client';

import React, { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  DEFAULT_LEVEL_COLORS,
  DEFAULT_LEVEL_ICONS,
  renderLevelIconOption,
} from '@/app/alarm/constants/level';
import LevelIcon from '@/app/alarm/components/levelIcon';
import { LevelFormItem } from '@/app/alarm/types/settings';
import { LevelItem } from '@/app/alarm/types/index';
import { NEUTRAL } from '@/app/alarm/constants/colors';
import {
  Grid,
  Modal,
  Form,
  InputNumber,
  Input,
  Select,
  ColorPicker,
  Segmented,
  Upload,
  Button,
  message,
} from 'antd';
import type { FormInstance } from 'antd';
import { CheckOutlined, UploadOutlined } from '@ant-design/icons';

const isCustomIconValue = (icon?: string) => !!icon?.startsWith('data:image/');

interface LevelFormModalProps {
  open: boolean;
  form: FormInstance<LevelFormItem>;
  editingLevel: LevelItem | null;
  currentLevelType: 'event' | 'alert' | 'incident';
  submitting: boolean;
  onCancel: () => void;
  onSubmit: () => void;
}

export default function LevelFormModal({
  open,
  form,
  editingLevel,
  currentLevelType,
  submitting,
  onCancel,
  onSubmit,
}: LevelFormModalProps) {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const [iconMode, setIconMode] = useState<'preset' | 'upload'>('preset');
  const isCompactModalForm = !screens.sm;

  useEffect(() => {
    if (!open) {
      setIconMode('preset');
      return;
    }

    const icon = form.getFieldValue('icon');
    setIconMode(isCustomIconValue(icon) ? 'upload' : 'preset');
  }, [open, form, editingLevel, currentLevelType]);

  const beforeIconUpload = async (file: File) => {
    const isAllowed = [
      'image/png',
      'image/jpeg',
      'image/jpg',
      'image/svg+xml',
    ].includes(file.type);
    if (!isAllowed) {
      message.error(t('settings.globalConfig.uploadTip'));
      return Upload.LIST_IGNORE;
    }

    const isLt200Kb = file.size / 1024 <= 200;
    if (!isLt200Kb) {
      message.error(t('settings.globalConfig.uploadTip'));
      return Upload.LIST_IGNORE;
    }

    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('read-failed'));
      reader.readAsDataURL(file);
    });

    form.setFieldValue('icon', dataUrl);
    setIconMode('upload');
    return Upload.LIST_IGNORE;
  };

  const handleIconModeChange = (nextMode: 'preset' | 'upload') => {
    setIconMode(nextMode);
    const currentIcon = form.getFieldValue('icon');

    if (nextMode === 'preset') {
      if (!currentIcon || isCustomIconValue(currentIcon)) {
        form.setFieldValue('icon', DEFAULT_LEVEL_ICONS[0]);
      }
      return;
    }

    if (!isCustomIconValue(currentIcon)) {
      form.setFieldValue('icon', '');
    }
  };

  return (
    <Modal
      title={
        editingLevel
          ? t('settings.globalConfig.editLevelTitle')
          : t('settings.globalConfig.addLevelTitle')
      }
      width={580}
      centered
      open={open}
      onCancel={onCancel}
      onOk={onSubmit}
      confirmLoading={submitting}
      styles={{ body: { paddingTop: 20, paddingBottom: 20 } }}
      destroyOnHidden
    >
      <Form
        form={form}
        layout={isCompactModalForm ? 'vertical' : 'horizontal'}
        labelCol={isCompactModalForm ? undefined : { flex: '90px' }}
        wrapperCol={isCompactModalForm ? undefined : { flex: 'auto' }}
        labelAlign="right"
        style={{ marginTop: 4 }}
      >
        <Form.Item
          name="level_id"
          label={t('settings.globalConfig.levelId')}
          style={{ marginBottom: 24 }}
          rules={[
            {
              required: true,
              message: t('settings.globalConfig.nonNegativeInteger'),
            },
            {
              validator: async (_, value) => {
                if (value === undefined || value === null || value === '') {
                  return;
                }
                if (
                  Number.isNaN(Number(value)) ||
                  Number(value) < 0 ||
                  !Number.isInteger(Number(value))
                ) {
                  throw new Error(t('settings.globalConfig.nonNegativeInteger'));
                }
              },
            },
          ]}
        >
          <InputNumber
            min={0}
            precision={0}
            style={{ width: '100%' }}
            disabled={!!editingLevel}
          />
        </Form.Item>
        <Form.Item
          name="level_display_name"
          label={t('settings.globalConfig.levelName')}
          style={{ marginBottom: 24 }}
          rules={[
            {
              required: true,
              message: t('common.inputTip') + t('settings.globalConfig.levelName'),
            },
          ]}
        >
          <Input maxLength={32} />
        </Form.Item>
        <Form.Item
          name="color"
          rules={[
            {
              required: true,
              message: t('common.selectTip') + t('settings.globalConfig.levelColor'),
            },
          ]}
          hidden
        >
          <Input />
        </Form.Item>
        <Form.Item
          required
          label={t('settings.globalConfig.levelColor')}
          style={{ marginBottom: 24 }}
        >
          <Form.Item shouldUpdate noStyle>
            {() => {
              const selectedColor =
                form.getFieldValue('color') || DEFAULT_LEVEL_COLORS[0];
              return (
                <div className="flex items-center gap-2">
                  <Select
                    value={selectedColor}
                    className="flex-1"
                    onChange={(value) => form.setFieldValue('color', value)}
                    options={DEFAULT_LEVEL_COLORS.map((color) => ({
                      value: color,
                      label: (
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-block h-4 w-4 rounded-full border border-[#E5E7EB]"
                            style={{ backgroundColor: color }}
                          />
                          <span>{color}</span>
                        </div>
                      ),
                    }))}
                  />
                  <ColorPicker
                    value={selectedColor}
                    presets={[
                      {
                        label: t('settings.globalConfig.levelColor'),
                        colors: DEFAULT_LEVEL_COLORS,
                      },
                    ]}
                    onChange={(color) =>
                      form.setFieldValue(
                        'color',
                        color.toHexString().toUpperCase(),
                      )
                    }
                  />
                </div>
              );
            }}
          </Form.Item>
        </Form.Item>
        <Form.Item
          label={t('settings.globalConfig.levelIcon')}
          required
          style={{ marginBottom: 0 }}
          className="align-top"
        >
          <Form.Item
            name="icon"
            rules={[
              {
                required: true,
                message: t('settings.globalConfig.iconRequired'),
              },
            ]}
            noStyle
          >
            <input type="hidden" />
          </Form.Item>
          <div className="w-full">
            <div className="mb-6 flex items-start">
              <Segmented
                size="middle"
                className="h-9 items-center"
                style={{ alignSelf: 'flex-start' }}
                value={iconMode}
                onChange={(value) =>
                  handleIconModeChange(value as 'preset' | 'upload')
                }
                options={[
                  {
                    label: t('settings.globalConfig.defaultIcons'),
                    value: 'preset',
                  },
                  {
                    label: t('settings.globalConfig.customUpload'),
                    value: 'upload',
                  },
                ]}
              />
            </div>
            {iconMode === 'preset' ? (
              <Form.Item shouldUpdate noStyle>
                {() => {
                  const selectedIcon = form.getFieldValue('icon');
                  const selectedColor = form.getFieldValue('color');
                  return (
                    <div className="grid grid-cols-5 gap-3">
                      {DEFAULT_LEVEL_ICONS.map((icon) => {
                        const isActive = selectedIcon === icon;
                        return (
                          <button
                            key={icon}
                            type="button"
                            className={`relative flex h-12 cursor-pointer items-center justify-center rounded-xl border transition-all ${
                              isActive
                                ? 'border-[#BFD3FF] bg-[#F7FAFF]'
                                : 'border-(--color-border-1) bg-white hover:border-[#9DBBFF] hover:bg-[#FAFBFF]'
                            }`}
                            onClick={() => form.setFieldValue('icon', icon)}
                          >
                            {isActive && (
                              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#2F6BFF] text-white shadow-sm ring-2 ring-white">
                                <CheckOutlined className="text-[9px]" />
                              </span>
                            )}
                            {renderLevelIconOption(icon, selectedColor)}
                          </button>
                        );
                      })}
                    </div>
                  );
                }}
              </Form.Item>
            ) : (
              <div>
                <Upload
                  showUploadList={false}
                  beforeUpload={(file) => beforeIconUpload(file as File)}
                >
                  <Button icon={<UploadOutlined />}>
                    {t('settings.globalConfig.uploadIcon')}
                  </Button>
                </Upload>
                <div className="mt-4 text-[12px] text-[var(--color-text-3)]">
                  {t('settings.globalConfig.uploadTip')}
                </div>
                <Form.Item shouldUpdate noStyle>
                  {() => {
                    const icon = form.getFieldValue('icon');
                    const selectedColor =
                      form.getFieldValue('color') || DEFAULT_LEVEL_COLORS[0];
                    return isCustomIconValue(icon) ? (
                      <div className="mt-4">
                        <div
                          className="inline-flex h-12 min-w-12 items-center justify-center rounded-xl border border-[#BFD3FF] bg-[#F7FAFF] px-4"
                          style={{
                            borderColor:
                              'color-mix(in srgb, var(--color-primary) 22%, white)',
                          }}
                        >
                          <span
                            className="flex h-7 w-7 items-center justify-center rounded-md"
                            style={{ backgroundColor: selectedColor }}
                          >
                            <LevelIcon
                              icon={icon}
                              className="h-4 w-4"
                              style={{ color: NEUTRAL.ON_DARK_FG }}
                            />
                          </span>
                        </div>
                      </div>
                    ) : null;
                  }}
                </Form.Item>
              </div>
            )}
          </div>
        </Form.Item>
      </Form>
    </Modal>
  );
}
