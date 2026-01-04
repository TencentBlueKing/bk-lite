"use client";
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Button, Popover, Skeleton, Form, message, Input, Tag } from 'antd';
import { CloseOutlined, PlusOutlined, HolderOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import Icon from '@/components/icon';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { useTheme } from '@/context/theme';
import { useLocale } from '@/context/locale';
import { ClientData, AppConfigItem } from '@/types/index';
import OperateModal from '@/components/operate-modal'
import { useUserInfoContext } from '@/context/userInfo';
import styles from './index.module.scss';

const ControlPage = () => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const { clientData, appConfigList, loading, appConfigLoading, refreshAppConfig } = useClientData();
  const { loading: userLoading, isFirstLogin, userId } = useUserInfoContext();
  const [isPopoverVisible, setIsPopoverVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [form] = Form.useForm();
  const { themeName } = useTheme();
  const { locale } = useLocale();
  const [overlayBgClass, setOverlayBgClass] = useState<string>('bg-[url(/app/console_bg.jpg)]');
  const colorOptions = ['blue', 'geekblue', 'purple'];

  // 自定义设置相关状态
  const [customSettingsVisible, setCustomSettingsVisible] = useState<boolean>(false);
  const [addedApps, setAddedApps] = useState<ClientData[]>([]);
  const [customSettingsLoading, setCustomSettingsLoading] = useState<boolean>(false);

  // 拖拽相关状态
  const [draggedItem, setDraggedItem] = useState<ClientData | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const draggedIndexRef = useRef<number | null>(null);

  const isDemoEnv = process.env.NEXT_PUBLIC_IS_DEMO_ENV === 'true';
  const zhlocale = locale === 'zh-CN';

  const displayApps = (appConfigList.length > 0 ? appConfigList : clientData).filter(item => item.name !== 'ops-console');

  useEffect(() => {
    if (appConfigLoading || loading) return;

    if (appConfigList.length > 0) {
      setAddedApps(appConfigList);
    } else {
      setAddedApps(clientData);
    }
  }, [clientData, appConfigList, appConfigLoading, loading]);

  const availableApps = clientData.filter(
    item => !addedApps.some(added => added.id === item.id)
  );

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


  const handleCustomSettingsCancel = () => {
    setAddedApps(appConfigList.length > 0 ? appConfigList : clientData);
    setCustomSettingsVisible(false);
  };

  const handleCustomSettingsSave = async () => {
    try {
      setCustomSettingsLoading(true);
      const appConfigListToSave: AppConfigItem[] = addedApps.map((app, index) => ({
        ...app,
        index,
      }));
      await post('/console_mgmt/user_app_sets/configure_user_apps/', {
        app_config_list: appConfigListToSave,
      });
      message.success(t('common.saveSuccess'));
      refreshAppConfig();
      setCustomSettingsVisible(false);
    } catch (error) {
      console.error(error);
    } finally {
      setCustomSettingsLoading(false);
    }
  };

  const handleAddApp = useCallback((app: ClientData) => {
    setAddedApps(prev => [...prev, app]);
  }, []);

  const handleRemoveApp = useCallback((appId: string) => {
    setAddedApps(prev => prev.filter(app => app.id !== appId));
  }, []);

  const handleDragStart = useCallback((e: React.DragEvent, app: ClientData, index: number) => {
    setDraggedItem(app);
    draggedIndexRef.current = index;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', app.id);
  }, []);

  // 拖拽经过
  const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (draggedIndexRef.current !== null && draggedIndexRef.current !== index) {
      setDragOverIndex(index);
    }
  }, []);

  // 拖拽离开 - 仅在真正离开容器时才清除
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    const relatedTarget = e.relatedTarget as HTMLElement;
    const currentTarget = e.currentTarget as HTMLElement;
    // 如果离开后进入的元素不是当前元素的子元素，则清除状态
    if (!currentTarget.contains(relatedTarget)) {
      setDragOverIndex(null);
    }
  }, []);

  // 放置
  const handleDrop = useCallback((e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    const sourceIndex = draggedIndexRef.current;

    if (sourceIndex === null || sourceIndex === targetIndex) {
      setDragOverIndex(null);
      return;
    }

    setAddedApps(prev => {
      const newApps = [...prev];
      const [draggedApp] = newApps.splice(sourceIndex, 1);
      newApps.splice(targetIndex, 0, draggedApp);
      return newApps;
    });

    setDragOverIndex(null);
    setDraggedItem(null);
    draggedIndexRef.current = null;
  }, []);

  // 拖拽结束
  const handleDragEnd = useCallback(() => {
    setDraggedItem(null);
    setDragOverIndex(null);
    draggedIndexRef.current = null;
  }, []);

  const getDragIndicatorPosition = useCallback((index: number): 'left' | 'right' | null => {
    if (draggedIndexRef.current === null || dragOverIndex === null) return null;
    if (dragOverIndex !== index) return null;
    if (draggedIndexRef.current > dragOverIndex) return 'left';
    if (draggedIndexRef.current < dragOverIndex) return 'right';
    return null;
  }, [dragOverIndex]);

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
          <div className="flex items-center mb-6 gap-6">
            <div className="flex items-center border border-[var(--color-border-1)] rounded-3xl w-[180px] text-sm">
              <span className="bg-[var(--color-text-2)] text-white px-4 py-1 rounded-2xl mr-2">{t('opsConsole.date')}</span>
              <span className="text-[var(--color-text-3)]">{dayjs().format("YYYY/MM/DD")}</span>
            </div>
            {!(loading || userLoading || appConfigLoading) && (
              <span
                className='bg-[var(--color-primary)] text-white px-4 py-1 rounded-2xl cursor-pointer transition-colors'
                onClick={() => setCustomSettingsVisible(true)}
              >
                {t('opsConsole.customSettings')}
              </span>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-6">
          {(loading || userLoading || isFirstLogin || appConfigLoading) ? (
            Array.from({ length: 10 }).map((_, index) => (
              <div key={index} className="bg-[var(--color-bg)] p-4 rounded shadow-md flex flex-col justify-between relative h-[230px]">
                <Skeleton active paragraph={{ rows: 4 }} />
              </div>
            ))
          ) : (
            displayApps.map((cardData: ClientData, index: number) => (
              <div
                key={index}
                className="bg-[var(--color-bg)] p-4 rounded shadow-md flex flex-col justify-between relative"
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
                <div className="flex flex-col items-start mb-2">
                  <div className="flex items-center mb-2">
                    <Icon type={cardData.icon || cardData.name} className="text-6xl mb-2 mr-2" />
                    <h2 className="text-xl font-bold mb-2">{cardData.display_name}</h2>
                  </div>
                  <div className="flex items-center flex-wrap">
                    {
                      cardData.tags?.map((tag: string) => (
                        <Tag key={tag} color={getRandomColor()} className="mb-1 mr-1 font-mini">
                          {tag}
                        </Tag>
                      ))
                    }
                  </div>
                </div>
                <p
                  className="text-[var(--color-text-3)] overflow-hidden text-ellipsis line-clamp-2 text-sm leading-5"
                  style={{ height: "2.5rem" }}
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

      {/* 自定义设置对话框 */}
      <OperateModal
        title={t('opsConsole.customSettings')}
        visible={customSettingsVisible}
        onCancel={handleCustomSettingsCancel}
        width={800}
        footer={[
          <Button key="cancel" onClick={handleCustomSettingsCancel}>
            {t('common.cancel')}
          </Button>,
          <Button key="save" type="primary" loading={customSettingsLoading} onClick={handleCustomSettingsSave}>
            {t('common.save')}
          </Button>
        ]}
      >
        <div className="py-4">
          <div className="mb-6">
            <div className="text-[var(--color-text-2)] mb-3">{t('opsConsole.added')}</div>
            <div className="flex flex-wrap gap-3">
              {addedApps.map((app, index) => {
                const indicatorPosition = getDragIndicatorPosition(index);
                return (
                  <div
                    key={app.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, app, index)}
                    onDragOver={(e) => handleDragOver(e, index)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, index)}
                    onDragEnd={handleDragEnd}
                    className={`
                      ${styles.dragIndicator} flex items-center gap-2 px-3 py-1.5 rounded-md cursor-move transition-all
                      bg-blue-50
                      ${draggedItem?.id === app.id ? 'opacity-50' : ''}
                      ${indicatorPosition === 'left' ? styles.activeLeft : ''}
                      ${indicatorPosition === 'right' ? styles.activeRight : ''}
                    `}
                  >
                    <HolderOutlined className="text-[var(--color-primary)] cursor-grab" />
                    <Icon type={app.icon || app.name} className="text-lg text-[var(--color-primary)]" />
                    <span className="text-[var(--color-primary)]">{app.display_name}</span>
                    {app.name !== "ops-console" && <CloseOutlined
                      className="text-[var(--color-primary)] hover:text-gray-400 cursor-pointer text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveApp(app.id);
                      }}
                    />}
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="text-[var(--color-text-2)] mb-3">{t('opsConsole.availableApps')}</div>
            <div className="flex flex-wrap gap-3">
              {availableApps.map((app) => (
                <div
                  key={app.id}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary)] transition-colors"
                >
                  <Icon type={app.icon || app.name} className="text-lg text-[var(--color-primary)]" />
                  <span className="text-[var(--color-text-1)]">{app.display_name}</span>
                  <PlusOutlined
                    className="text-[var(--color-text-3)] hover:text-[var(--color-primary)] cursor-pointer"
                    onClick={() => handleAddApp(app)}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </OperateModal>
    </>
  );
};

export default ControlPage;
