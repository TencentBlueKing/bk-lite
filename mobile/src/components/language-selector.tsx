'use client';
import React, { useState } from 'react';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { ActionSheet, List, Toast } from 'antd-mobile';
import { CheckOutline, GlobalOutline } from 'antd-mobile-icons';
import { LanguageOption, LanguageSelectorProps } from '@/types/common';

const languages: LanguageOption[] = [
  {
    key: 'zh-CN',
    label: '简体中文',
    nativeLabel: '简体中文',
  },
  {
    key: 'en',
    label: 'English',
    nativeLabel: 'English',
  },
];

export default function LanguageSelector({ onSelect }: LanguageSelectorProps) {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocale();
  const [visible, setVisible] = useState(false);

  const currentLanguage =
    languages.find((lang) => lang.key === locale) || languages[0];

  const handleLanguageChange = async (language: LanguageOption) => {
    try {
      setLocale(language.key);
      onSelect?.(language.key);
      setVisible(false);

      Toast.show({
        content: `${t('common.switchedToLanguage')}${language.label}`,
        icon: 'success',
        position: 'center',
      });
    } catch (error) {
      console.error('切换语言失败:', error);
      Toast.show({
        content: t('common.switchLanguageFailed'),
        icon: 'fail',
        position: 'center',
      });
    }
  };

  const actions = languages.map((language) => ({
    key: language.key,
    text: (
      <div className="flex items-center justify-between w-full px-4 py-1">
        <div className="flex flex-col items-start">
          <span className="text-sm font-medium text-[var(--color-text-1)]">
            {language.label}
          </span>
          <span className="text-xs text-[var(--color-text-3)] mt-0.5">
            {language.nativeLabel}
          </span>
        </div>
        {locale === language.key && (
          <CheckOutline className="text-[var(--color-primary)] text-base ml-3" />
        )}
      </div>
    ),
    onClick: () => handleLanguageChange(language),
  }));

  return (
    <>
      <List.Item
        prefix={
          <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
            <GlobalOutline className="text-[var(--color-primary)] text-base" />
          </div>
        }
        extra={
          <div className="flex items-center">
            <span className="text-[var(--color-text-3)] text-xs mr-2">
              {currentLanguage.label}
            </span>
          </div>
        }
        onClick={() => setVisible(true)}
        clickable
      >
        <span className="text-[var(--color-text-1)] text-sm font-medium">
          {t('common.languageSettings')}
        </span>
      </List.Item>

      <ActionSheet
        visible={visible}
        actions={actions}
        onClose={() => setVisible(false)}
        closeOnAction={false}
        extra={
          <div className="text-center py-2">
            <div className="text-base font-semibold text-[var(--color-text-1)] mb-0.5">
              {t('common.languageSelectionTitle')}
            </div>
            <div className="text-xs text-[var(--color-text-3)]">
              {t('common.languageSelectionSubtitle')}
            </div>
          </div>
        }
        styles={{
          body: {
            paddingTop: 0,
          },
        }}
      />
    </>
  );
}
