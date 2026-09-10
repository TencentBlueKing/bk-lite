'use client';

import React, { useEffect, useState } from 'react';
import { Spin, Tooltip, Button, Input, Checkbox, Space } from 'antd';
import { SearchOutlined, ExportOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import Icon from '@/components/icon';
import OperateModal from '@/components/operate-modal';
import {
  resolveOptionIcon,
  type SelectorOption,
} from '@/app/opspilot/components/opspilot-selector-shared';
import { useTranslation } from '@/utils/i18n';

interface OpspilotSelectorOperateModalProps {
  visible: boolean;
  okText?: string;
  title?: string;
  cancelText?: string;
  options: SelectorOption[];
  selectedOptions: number[];
  loading?: boolean;
  isNeedGuide?: boolean;
  showToolDetail?: boolean;
  onOk: (selected: number[]) => void;
  onCancel: () => void;
}

const OpspilotSelectorOperateModal: React.FC<
  OpspilotSelectorOperateModalProps
> = ({
  visible,
  okText,
  title,
  cancelText,
  options,
  selectedOptions,
  loading = false,
  isNeedGuide = true,
  showToolDetail = false,
  onOk,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [tempSelectedOptions, setTempSelectedOptions] = useState<number[]>([]);
  const [searchTerm, setSearchTerm] = useState<string>('');

  useEffect(() => {
    if (visible) {
      setTempSelectedOptions(selectedOptions);
      setSearchTerm('');
    }
  }, [visible, selectedOptions]);

  const handleOptionSelect = (id: number) => {
    setTempSelectedOptions((prev) =>
      prev.includes(id)
        ? prev.filter((item) => item !== id)
        : [...prev, id],
    );
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value.toLowerCase());
  };

  const handleConfigureOptions = () => {
    window.open('/opspilot/knowledge', '_blank');
  };

  const filteredOptions = options.filter((option) => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return true;
    return (
      option.name?.toLowerCase().includes(keyword) ||
      option.description?.toLowerCase().includes(keyword)
    );
  });

  return (
    <OperateModal
      title={title || t('skill.selectKnowledgeBase')}
      open={visible}
      onCancel={onCancel}
      width={720}
      footer={
        <div className="flex w-full items-center justify-between">
          <div className="text-xs text-[var(--color-text-3)]">
            {t('skill.selectedCount', '已选择数量')}:{' '}
            <span className="font-semibold tabular-nums text-[var(--color-text-1)]">
              {tempSelectedOptions.length}
            </span>
          </div>
          <Space>
            <Button onClick={onCancel}>{cancelText || t('common.cancel')}</Button>
            <Button type="primary" onClick={() => onOk(tempSelectedOptions)}>
              {okText || t('common.confirm')}
            </Button>
          </Space>
        </div>
      }
    >
      <Spin spinning={loading}>
        {options.length === 0 ? (
          isNeedGuide ? (
            <div className="py-8 text-center">
              <p className="text-sm text-[var(--color-text-3)]">{t('skill.settings.noKnowledgeBase')}</p>
              <Button type="link" onClick={handleConfigureOptions} className="p-0">
                {t('skill.settings.clickHere')}
              </Button>
              <span className="text-sm text-[var(--color-text-3)]">
                {t('skill.settings.toConfigureKnowledgeBase')}
              </span>
            </div>
          ) : (
            <CompactEmptyState
              description={t('common.noData')}
              className="py-8"
            />
          )
        ) : (
          <>
            <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--color-text-3)]">
                  {t('common.total', '共')} {filteredOptions.length} {t('tool.items', '项')}
                </span>
                {tempSelectedOptions.length > 0 && (
                  <span className="inline-flex h-5 items-center rounded-full bg-[var(--color-count-alt-bg)] px-2 text-[11px] font-medium tabular-nums text-[var(--color-count-alt)]">
                    已选 {tempSelectedOptions.length} 项
                  </span>
                )}
              </div>
              <Input
                allowClear
                className="w-64"
                placeholder={`${t('common.search')}...`}
                prefix={<SearchOutlined className="text-[var(--color-text-4)]" />}
                value={searchTerm}
                onChange={handleSearch}
              />
            </div>
            {filteredOptions.length === 0 ? (
              <div className="py-8">
                <CompactEmptyState description={t('common.noData')} />
              </div>
            ) : (
              <div className="grid max-h-[440px] grid-cols-1 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
                {filteredOptions.map((option) => {
                  const isSelected = tempSelectedOptions.includes(option.id);
                  const resolvedIcon = resolveOptionIcon(option.name, option.icon);
                  return (
                    <div
                      key={option.id}
                      role="button"
                      tabIndex={0}
                      aria-pressed={isSelected}
                      className={`group relative flex flex-col justify-between rounded-lg border p-3.5 cursor-pointer transition-all duration-150 select-none ${
                        isSelected
                          ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]/45 shadow-2xs'
                          : 'border-[var(--color-border-1)] bg-[var(--color-bg)] hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-fill-1)]/40'
                      }`}
                      onClick={() => handleOptionSelect(option.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleOptionSelect(option.id);
                        }
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2.5">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-fill-1)] text-[var(--color-primary)] transition-colors group-hover:bg-[var(--color-fill-2)]">
                            <Icon type={resolvedIcon} className="text-xl" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <Tooltip title={option.name}>
                              <div className="truncate text-[13px] font-semibold leading-snug text-[var(--color-text-1)]">
                                {option.name}
                              </div>
                            </Tooltip>
                          </div>
                        </div>
                        <div className="shrink-0 pt-0.5" onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={isSelected}
                            onChange={() => handleOptionSelect(option.id)}
                          />
                        </div>
                      </div>

                      <div className="mt-2 min-h-[36px]">
                        <p className="line-clamp-2 text-xs leading-relaxed text-[var(--color-text-3)] m-0">
                          {option.description || t('skill.toolDescriptionDefault', '提供智能体外部接口调用与自动化能力')}
                        </p>
                      </div>

                      {showToolDetail && (
                        <div className="mt-2 flex items-center justify-end border-t border-[var(--color-border-1)]/40 pt-2">
                          <a
                            href={`/opspilot/tool?id=${option.id}&name=${encodeURIComponent(option.name || '')}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-[var(--color-primary)] hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {t('common.viewDetails')}
                            <ExportOutlined className="text-[10px]" />
                          </a>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </Spin>
    </OperateModal>
  );
};

export type { OpspilotSelectorOperateModalProps };
export default OpspilotSelectorOperateModal;
