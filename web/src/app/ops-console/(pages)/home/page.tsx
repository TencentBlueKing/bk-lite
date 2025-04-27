"use client";
import React, { useState, useEffect } from 'react';
import { Button, Popover, Skeleton, Form, message, Input, Tag } from 'antd';
import dayjs from 'dayjs';
import Icon from '@/components/icon';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { useTheme } from '@/context/theme';
import { useLocale } from '@/context/locale';
import { CLIENT_TAGS_MAP } from '@/app/ops-console/constants/client';
import OperateModal from '@/components/operate-modal'
import { useUserInfoContext } from '@/context/userInfo';


interface CardData {
  name: string;
  description: string;
  url: string;
  client_id: string;
}

const ControlPage = () => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const { clientData, loading } = useClientData();
  const { loading: userLoading, isFirstLogin, userId } = useUserInfoContext();
  const [isPopoverVisible, setIsPopoverVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [form] = Form.useForm();
  const { themeName } = useTheme();
  const { locale } = useLocale();
  const [overlayBgClass, setOverlayBgClass] = useState<string>('bg-[url(/app/console_bg.jpg)]');
  const colorOptions = ['blue', 'geekblue', 'purple'];

  const isDemoEnv = process.env.NEXT_PUBLIC_IS_DEMO_ENV === 'true';
  const zhlocale = locale === 'zh-CN';

  useEffect(() => {
    const consoleContainer = document.querySelector('.console-container');
    const parentElement = consoleContainer?.parentElement;

    if (parentElement) {
      parentElement.style.padding = '0';
      return () => {
        // clean padding style when component unmount
        try {
          if (document.contains(parentElement)) {
            parentElement.style.padding = '';
          }
        } catch (e) {
          console.log('clean padding:', e);
        }
      };
    }
  }, []);

  useEffect(() => {
    setOverlayBgClass(themeName === 'dark' ? 'bg-[url(/app/console_bg_dark.jpg)]' : 'bg-[url(/app/console_bg.jpg)]');
  }, [themeName]);

  const getRandomColor = () => {
    return colorOptions[Math.floor(Math.random() * colorOptions.length)];
  }

  const handleApplyDemoClick = () => {
    window.open('https://www.canway.net/apply.html', '_blank');
  };

  const handleContactUsClick = () => {
    setIsPopoverVisible(!isPopoverVisible);
  };

  const popoverContent = (
    <>
      <div className="border-b border-[var(--color-border-1)]">
        <div className="flex items-center mb-2">
          <Icon type="dadianhua" className="mr-1 text-[var(--color-primary)]" />
          <span>{t('opsConsole.serviceHotline')}:</span>
        </div>
        <p className="text-blue-600 mb-4">020-38847288</p>
      </div>
      <div className="pt-4">
        <div className="flex items-center mb-2">
          <Icon type="qq" className="mr-1 text-[var(--color-primary)]" />
          <span>{t('opsConsole.qqConsultation')}:</span>
        </div>
        <p className="text-blue-600">3593213400</p>
      </div>
    </>
  );

  const handleCardClick = (url: string) => {
    window.open(url, '_blank');
  };

  const handleOk = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      await post('/console_mgmt/init_user_set/', {
        group_name: values.group_name,
        user_id: userId,
      });
      message.success(t('common.saveSuccess'));
      window.location.reload();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <>
      <div
        className={`relative w-full h-full flex flex-col p-12 console-container ${overlayBgClass}`}
        style={{
          backgroundSize: "cover",
          backgroundPosition: "top",
          minHeight: "calc(100vh - 58px)",
        }}
      >
        <div className="mt-6 mb-10">
          <div className="w-full flex justify-between items-center">
            <div className="w-full">
              <h1 className="text-3xl font-bold mb-4">{t('opsConsole.console')}</h1>
              <p className="text-[var(--color-text-2)] mb-4 w-1/2 break-words">
                {t('opsConsole.description')}
              </p>
            </div>
            {isDemoEnv && (
              <div className="absolute right-4 top-4 flex flex-col text-sm">
                <div
                  onClick={handleApplyDemoClick}
                  className={`bg-gradient-to-b from-blue-500 tracking-[3px] to-indigo-600 text-white rounded-3xl shadow-md flex items-center justify-center mb-2 cursor-pointer py-1 ${zhlocale ? 'w-[32px]' : 'px-1'}`}
                  style={zhlocale ? {
                    writingMode: "vertical-rl",
                    textOrientation: "upright",
                  } : {}}
                >
                  {t('opsConsole.freeApply')}
                </div>
                <Popover
                  content={popoverContent}
                  visible={isPopoverVisible}
                  trigger="click"
                  placement="left"
                  onVisibleChange={setIsPopoverVisible}
                >
                  <div
                    onClick={handleContactUsClick}
                    className={`bg-gradient-to-b from-blue-500 tracking-[3px] to-indigo-600 text-white rounded-3xl shadow-md flex items-center justify-center mb-2 cursor-pointer py-1 ${zhlocale ? 'w-[32px]' : 'px-1'}`}
                    style={zhlocale ? {
                      writingMode: "vertical-rl",
                      textOrientation: "upright",
                    } : {}}
                  >
                    <Icon type="lianxiwomen1" className={`${zhlocale ? 'mb-1' : 'mr-1'}`} />
                    {t('opsConsole.contactUs')}
                  </div>
                </Popover>
              </div>
            )}
          </div>
          <div className="flex items-center mb-6 border border-[var(--color-border-1)] rounded-3xl w-[180px] text-sm">
            <span className="bg-[var(--color-text-2)] text-white px-4 py-1 rounded-2xl mr-2">{t('opsConsole.date')}</span>
            <span className="text-[var(--color-text-3)]">{dayjs().format("YYYY/MM/DD")}</span>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-6">
          {(loading || userLoading || isFirstLogin) ? (
            Array.from({ length: 10 }).map((_, index) => (
              <div key={index} className="bg-[var(--color-bg)] p-4 rounded shadow-md flex flex-col justify-between relative h-[230px]">
                <Skeleton active paragraph={{ rows: 4 }} />
              </div>
            ))
          ) : (
            clientData.filter(cardData => cardData.client_id !== "ops-console").map((cardData: CardData, index: number) => (
              <div
                key={index}
                className="bg-[var(--color-bg)] p-4 rounded shadow-md flex flex-col justify-between relative h-[190px]"
                onClick={() => handleCardClick(cardData.url)}
              >
                <div className="absolute top-6 right-4">
                  <Button
                    type="primary"
                    size="small"
                    className="flex items-center text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCardClick(cardData.url);
                    }}
                  >
                    {t('opsConsole.clickToEnter')}
                  </Button>
                </div>
                <div className="flex flex-col items-start">
                  <div className="flex items-center mb-2">
                    <Icon type={cardData.client_id} className="text-6xl mb-2 mr-2" />
                    <h2 className="text-xl font-bold mb-2">{cardData.name}</h2>
                  </div>
                  <div className="flex items-center flex-wrap">
                    {
                      CLIENT_TAGS_MAP[cardData.client_id]?.map((tag: string) => (
                        <Tag key={tag} color={getRandomColor()} className="mb-1 mr-1 font-mini">
                          {t(`opsConsole.${tag}`)}
                        </Tag>
                      ))
                    }
                  </div>
                </div>
                <p
                  className="text-[var(--color-text-3)] overflow-hidden text-ellipsis line-clamp-2 text-sm"
                  style={{ minHeight: "2.5rem" }}
                >
                  {cardData.description}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      <OperateModal
        title={t('opsConsole.initUserSet')}
        visible={isFirstLogin && !userLoading}
        closable={false}
        footer={[
          <Button key="submit" type="primary" loading={confirmLoading} onClick={handleOk}>
            {t('common.confirm')}
          </Button>
        ]}
      >
        <Form
          form={form}
          layout="vertical"
        >
          <Form.Item
            name="group_name"
            label={t('opsConsole.group')}
            rules={[
              { required: true, message: `${t('common.inputMsg')}${t('opsConsole.group')}` }
            ]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('opsConsole.group')}`} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default ControlPage;
