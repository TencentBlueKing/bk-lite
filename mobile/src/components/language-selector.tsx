'use client';
import React, { useState } from 'react';
import { useLocale } from '@/context/locale';
import { useAuth } from '@/context/auth';
import { useTranslation } from '@/utils/i18n';
import { ActionSheet, List, Toast, SpinLoading } from 'antd-mobile';
import { CheckOutline, GlobalOutline } from 'antd-mobile-icons';
import { LanguageOption, LanguageSelectorProps } from '@/types/common';
import { updateUserInfo as updateUserInfoApi } from '@/api/user';

const languages: LanguageOption[] = [
  {
    key: 'zh-Hans',
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
  const { updateUserInfo: updateStoredUserInfo } = useAuth();
  const [visible, setVisible] = useState(false);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);

  const currentLanguage =
    languages.find((lang) => lang.key === locale) || languages[0];

  const handleLanguageChange = async (language: LanguageOption) => {
    if (language.key === locale) return;
    if (updatingKey) return;

    try {
      setUpdatingKey(language.key);

      const response = await updateUserInfoApi({ locale: language.key });

      if (!response.result) {
        const errorMessage = response.message || t('common.switchLanguageFailed');
        Toast.show({
          content: errorMessage,
          icon: 'fail',
          position: 'center',
        });
        return;
      }

      await updateStoredUserInfo({ locale: language.key });

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
    } finally {
      setUpdatingKey(null);
    }
  };

  const actions = languages.map((language) => ({
    key: language.key,
    text: (
      <div className="flex items-center justify-between w-full px-4 py-1">
        <div className="flex flex-col items-start">
          <span className="text-base font-medium text-[var(--color-text-1)]">
            {language.label}
          </span>
          <span className="text-sm text-[var(--color-text-3)] mt-0.5">
            {language.nativeLabel}
          </span>
        </div>
        {updatingKey === language.key ? (
          <SpinLoading color="primary" style={{ '--size': '18px' }} className="ml-3" />
        ) : locale === language.key ? (
          <CheckOutline className="text-[var(--color-primary)] text-lg ml-3" />
        ) : null}
      </div>
    ),
    onClick: () => handleLanguageChange(language),
  }));

  return (
    <>
      <List.Item
        prefix={
          <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
            <GlobalOutline className="text-[var(--color-primary)] text-lg" />
          </div>
        }
        extra={
          <div className="flex items-center">
            <span className="text-[var(--color-text-3)] text-sm mr-2">
              {currentLanguage.label}
            </span>
          </div>
        }
        onClick={() => setVisible(true)}
        clickable
      >
        <span className="text-[var(--color-text-1)] text-base font-medium">
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
            <div className="text-lg font-semibold text-[var(--color-text-1)] mb-0.5">
              {t('common.languageSelectionTitle')}
            </div>
            <div className="text-sm text-[var(--color-text-3)]">
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
