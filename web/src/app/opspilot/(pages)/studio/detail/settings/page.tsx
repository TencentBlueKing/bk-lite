'use client';

import React, { useState, useEffect } from 'react';
import { Form, Input, Select, Button, Switch, Dropdown, Menu, Tag, Checkbox, message, Spin, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { DeleteOutlined, DownOutlined, CheckOutlined, StopOutlined } from '@ant-design/icons';
import useGroups from '@/app/opspilot/hooks/useGroups';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams } from 'next/navigation';
import { Skill } from '@/app/opspilot/types/skill';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import OperateModal from '@/app/opspilot/components/studio/operateModal';
import CustomChat from '@/app/opspilot/components/custom-chat';
import PermissionWrapper from '@/components/permission';
import styles from '@/app/opspilot/styles/common.module.scss';
import Icon from '@/components/icon';
import { useStudioApi } from '@/app/opspilot/api/studio';

const { Option } = Select;
const { TextArea } = Input;

const StudioSettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { groups } = useGroups();
  const [pageLoading, setPageLoading] = useState(true);
  const [saveLoading, setSaveLoading] = useState(false);
  const [rasaModels, setRasaModels] = useState<{ id: number; name: string; enabled: boolean }[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [channels, setChannels] = useState<{ id: number; name: string, enabled: boolean }[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<number[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<number[]>([]);
  const [originChannels, setOriginChannels] = useState<number[]>([]);
  const [isSkillModalVisible, setIsSkillModalVisible] = useState(false);
  const [isDomainEnabled, setIsDomainEnabled] = useState(false);
  const [isPortMappingEnabled, setIsPortMappingEnabled] = useState(false);
  const [botDomain, setBotDomain] = useState('');
  const [nodePort, setNodePort] = useState<number | string>(5005);
  const [enableSsl, setEnableSsl] = useState(false);
  const [online, setOnline] = useState(false);
  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : null;
  const { fetchInitialData, saveBotConfig, toggleOnlineStatus } = useStudioApi();

  const IconMap: any = {
    enterprise_wechat: 'qiwei2',
    wechat_official_account: 'weixingongzhonghao',
    ding_talk: 'dingding',
    web: 'icon-08',
    deepseek: 'a-deepseek1'
  }

  useEffect(() => {
    if (!botId) return;

    const fetchData = async () => {
      try {
        const [rasaModelsData, skillsData, channelsData, botData] = await fetchInitialData(botId);

        setRasaModels(rasaModelsData);
        setSkills(skillsData);
        setChannels(channelsData);

        let initialRasaModel = botData.rasa_model;
        if (!initialRasaModel && rasaModelsData.length > 0) {
          initialRasaModel = rasaModelsData[0].id;
        }

        form.setFieldsValue({
          name: botData.name,
          introduction: botData.introduction,
          group: botData.team,
          rasa_model: initialRasaModel,
          replica_count: botData.replica_count
        });

        setOnline(botData.online);
        setSelectedSkills(botData.llm_skills);
        setSelectedChannels(botData.channels);
        setOriginChannels(botData.channels);
        setIsDomainEnabled(botData.enable_bot_domain);
        setEnableSsl(botData.enable_ssl);
        setIsPortMappingEnabled(botData.enable_node_port);
        setBotDomain(botData.bot_domain);
        setNodePort(botData.node_port);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setPageLoading(false);
      }
    };

    fetchData();
  }, [botId]);

  const handleAddSkill = () => setIsSkillModalVisible(true);
  const handleDeleteSkill = (id: number) => setSelectedSkills(prev => prev.filter(item => item !== id));

  const handleSave = async (isPublish = false) => {
    setSaveLoading(true);
    try {
      const values = await form.validateFields();

      const payload = {
        channels: selectedChannels,
        name: values.name,
        introduction: values.introduction,
        team: values.group,
        replica_count: values.replica_count,
        enable_bot_domain: isDomainEnabled,
        bot_domain: isDomainEnabled ? botDomain : null,
        enable_ssl: isDomainEnabled ? enableSsl : false,
        enable_node_port: isPortMappingEnabled,
        node_port: isPortMappingEnabled ? nodePort : null,
        rasa_model: values.rasa_model,
        llm_skills: selectedSkills,
        is_publish: isPublish
      };

      await saveBotConfig(botId, payload);
      message.success(t(isPublish ? 'common.publishSuccess' : 'common.saveSuccess'));
      
      if (isPublish) {
        setOnline(true);
        setOriginChannels(selectedChannels);
      }
    } catch (error) {
      console.error(error);
      message.error(t('common.saveFailed'));
    } finally {
      setSaveLoading(false);
    }
  };

  const iconType = (index: number) => index % 2 === 0 ? 'jishuqianyan' : 'theory';

  const handleSaveAndPublish = () => handleSave(true);

  const toggleOnline = async () => {
    try {
      await toggleOnlineStatus(botId);
      setOnline(prevOnline => !prevOnline);
      message.success(t('common.saveSuccess'));
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const handleConfigureChannels = () => {
    const queryParams = new URLSearchParams(window.location.search);
    const url = `/opspilot/studio/detail/channel?${queryParams.toString()}`;
    window.open(url, '_blank');
  };

  const menu = (
    <Menu style={{ width: 300 }}>
      <Menu.Item key="info" disabled style={{ whiteSpace: 'normal', opacity: 1, cursor: 'default' }}>
        <div className="text-sm">{t('studio.settings.publishTip')} {t('studio.settings.selectedParams')}</div>
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="save_publish">
        <PermissionWrapper requiredPermissions={['Save&Publish']}>
          <Button type="primary" size="small" style={{ width: '100%' }} onClick={handleSaveAndPublish}>
            {t('common.save')} & {t('common.publish')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="save_only">
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button size="small" style={{ width: '100%' }} onClick={() => handleSave(false)}>
            {t('common.saveOnly')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      {online && (
        <Menu.Item key="offline" onClick={toggleOnline}>
          <div className="flex justify-end items-center">
            <span className="mr-[5px] text-gray-500">{t('studio.off')}</span>
            <Icon type="offline" />
          </div>
        </Menu.Item>
      )}
    </Menu>
  );

  const theme = typeof window !== 'undefined' && localStorage.getItem('theme');
  const overlayBgClass = theme === 'dark' ? 'bg-gray-950' : 'bg-white';

  const allChannelsDisabled = channels.every(channel => !channel.enabled);

  const showCustomChat = channels.filter(channel => originChannels.includes(channel.id)).some(channel => channel.name === 'web') && online;

  const handleSendMessage = async (newMessage: CustomChatMessage[], lastUserMessage?: CustomChatMessage): Promise<CustomChatMessage[]> => {
    return new Promise(async (resolve) => {
      const message = lastUserMessage || [...newMessage].reverse().find(message => message.role === 'user');
      if (!message) {
        resolve(newMessage);
        return;
      }
      try {
        const payload = {
          sender: "user",
          message: message?.content || '',
          port: nodePort || 5005,
          domain: botDomain,
          ssl: enableSsl,
          id: botId
        };
        const response = await fetch('/opspilot/api/webhook', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error('Network response was not ok');
        }

        const json = await response.json();
        if (Array.isArray(json) && json.length > 0) {
          const reply = json.reduce((acc, cur) => acc + cur.text, '');
          const botMessage: CustomChatMessage = {
            id: uuidv4(),
            content: reply,
            role: 'bot',
            createAt: new Date().toISOString(),
            updateAt: new Date().toISOString(),
            knowledgeBase: null,
          };

          resolve([...newMessage, botMessage]);
        } else {
          resolve(newMessage);
        }
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
        resolve(newMessage);
      }
    });
  };

  return (
    <div className="relative flex w-full">
      {(pageLoading || saveLoading) && (
        <div
          className={`absolute inset-0 flex justify-center items-center min-h-[500px] ${overlayBgClass} bg-opacity-50 z-50`}>
          <Spin size="large" />
        </div>
      )}
      {!pageLoading && (
        <div className={`w-full flex transition-all ${showCustomChat ? 'justify-between' : 'justify-center'}`}>
          <div className={`w-full sm:w-3/4 lg:w-2/3 xl:w-1/2 ${showCustomChat ? 'overflow-y-auto h-[calc(100vh-230px)]' : ''}`}>
            <div className="absolute top-0 right-0 flex items-center space-x-4">
              <Tag
                color={online ? 'green' : ''}
                className={`${styles.statusTag} ${online ? styles.online : styles.offline}`}
              >
                {online ? t('studio.on') : t('studio.off')}
              </Tag>
              <Dropdown overlay={menu} trigger={['click']}>
                <Button icon={<DownOutlined />} size="small" type="primary">
                  {t('common.settings')}
                </Button>
              </Dropdown>
            </div>
            <div className="space-y-4">
              <div className="mb-6">
                <h2 className="font-semibold mb-2 text-base">{t('studio.information')}</h2>
                <div className="px-4 pt-[24px] border rounded-md shadow-sm">
                  <Form form={form} labelCol={{ flex: '0 0 128px' }} wrapperCol={{ flex: '1' }}>
                    <Form.Item
                      label={t('studio.form.name')}
                      name="name"
                      rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.name')}` }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item
                      label={t('studio.form.group')}
                      name="group"
                      rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.group')}` }]}
                    >
                      <Select mode="multiple">
                        {groups.map((group) => (
                          <Option key={group.id} value={group.id}>
                            {group.name}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>
                    <Form.Item
                      label={t('studio.form.introduction')}
                      name="introduction"
                      rules={[{ required: true, message: `${t('common.inputMsg')}{t('studio.form.introduction')}` }]}
                    >
                      <TextArea rows={4} />
                    </Form.Item>
                    <Form.Item
                      label={t('studio.form.model')}
                      name="rasa_model"
                      tooltip={t('studio.form.modelTip')}
                      rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.model')}` }]}
                    >
                      <Select>
                        {rasaModels.map((model) => (
                          <Option key={model.id} value={model.id} disabled={!model.enabled}>
                            {model.name}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>
                    <Form.Item
                      label={t('studio.form.replicaCount')}
                      name="replica_count"
                      tooltip={t('studio.form.replicaCountTip')}
                      rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.replicaCount')}` }]}
                    >
                      <InputNumber
                        min={1}
                        style={{width: '100%'}}
                      />
                    </Form.Item>
                  </Form>
                </div>
              </div>
              <div className="mb-6">
                <h2 className="font-semibold mb-2 text-base">{t('skill.menu')}</h2>
                <div className="px-4 pt-4 border rounded-md shadow-sm">
                  <Form.Item className="mb-0">
                    <div className="mb-4 flex justify-end">
                      <Button type="dashed" onClick={handleAddSkill}>
                        + {t('common.add')}
                      </Button>
                    </div>
                    <div className={`grid ${selectedSkills.length ? 'mb-4' : ''}`}>
                      {selectedSkills.map((id, index) => {
                        const skill = skills.find((s) => s.id === id);
                        return skill ? (
                          <div key={id} className={`rounded-md px-4 py-2 flex items-center justify-between ${styles.cardFillColor}`}>
                            <div className='flex items-center'>
                              <Icon type={iconType(index)} className="text-xl mr-2" />
                              <span>{skill.name}</span>
                            </div>
                            <div className='hover:text-blue-500 hover:bg-blue-100 p-1 rounded'>
                              <DeleteOutlined onClick={() => handleDeleteSkill(id)} />
                            </div>
                          </div>
                        ) : null;
                      })}
                    </div>
                  </Form.Item>
                </div>
              </div>
              <div className="mb-6">
                <h2 className="font-semibold mb-2 text-base">{t('studio.channel.title')}</h2>
                <div className="px-4 pt-4 border rounded-md shadow-sm">
                  <Form.Item className="mb-4">
                    <div className="grid gap-3 grid-cols-3">
                      {channels.map((channel) => {
                        const isSelected = selectedChannels.includes(channel.id);
                        return (
                          <div
                            key={channel.id}
                            onClick={() => {
                              if (channel.enabled) {
                                setSelectedChannels((prev) =>
                                  isSelected
                                    ? prev.filter(id => id !== channel.id)
                                    : [...prev, channel.id]
                                );
                              }
                            }}
                            className={`relative flex items-center cursor-pointer rounded-md p-4 text-center
                              ${isSelected ? styles.selectedCommonItem : styles.cardFillColor}
                              ${channel.enabled ? '' : styles.disabledCommonItem}`
                            }
                          >
                            <Icon type={IconMap[channel.name]} className="text-3xl mr-[5px]" />
                            {channel.name}
                            {isSelected && <CheckOutlined className={`${styles.checkedIcon}`} />}
                            {!channel.enabled && <StopOutlined className={`${styles.disabledIcon}`} />}
                          </div>
                        );
                      })}
                    </div>
                    {allChannelsDisabled ? (<div className="mt-3">
                      {t('studio.settings.noChannelHasBeenOpened')}
                      <a onClick={handleConfigureChannels} style={{ color: 'var(--color-primary)', cursor: 'pointer' }}>
                        {t('studio.settings.clickHere')}
                      </a>
                      {t('studio.settings.toConfigureChannels')}
                    </div>) : (<div className='mt-5'>
                      <div className="mb-5">
                        <div className="flex items-center justify-between">
                          <span className='text-sm'>{t('studio.settings.domain')}</span>
                          <Switch size="small" checked={isDomainEnabled} onChange={(checked) => {
                            setIsDomainEnabled(checked);
                            if (!checked) {
                              setBotDomain('');
                              setEnableSsl(false);
                            }
                          }} />
                        </div>
                        {isDomainEnabled && (
                          <>
                            <Form.Item className='mt-4 mb-0'>
                              <div className='w-full flex items-center'>
                                <Input
                                  className='flex-1 mr-3'
                                  placeholder={`${t('common.inputMsg')}${t('studio.settings.domain')}`}
                                  value={botDomain}
                                  onChange={(e) => setBotDomain(e.target.value)}
                                />
                                <Checkbox
                                  checked={enableSsl}
                                  onChange={(e) => setEnableSsl(e.target.checked)}
                                >
                                  {t('studio.settings.enableSsl')}
                                </Checkbox>
                              </div>
                            </Form.Item>
                          </>
                        )}
                      </div>
                      <div className="border-t border-[var(--color-border-1)] py-4">
                        <div className="flex items-center justify-between">
                          <span className='text-sm'>{t('studio.settings.portMapping')}</span>
                          <Switch size="small" checked={isPortMappingEnabled} onChange={(checked) => {
                            setIsPortMappingEnabled(checked);
                            if (!checked) {
                              setNodePort(5005);
                            }
                          }} />
                        </div>
                        {isPortMappingEnabled && (
                          <Form.Item className="mt-4 mb-0">
                            <Input
                              placeholder={`${t('common.inputMsg')}${t('studio.settings.portMapping')}`}
                              value={nodePort}
                              onChange={(e) => {
                                const value = Number(e.target.value);
                                // 端口号的合法范围为 1-65535
                                if (!Number.isNaN(value) && value > 0 && value <= 65535) {
                                  setNodePort(value);
                                } else if (e.target.value === '') {
                                  setNodePort('');
                                }
                              }}
                            />
                          </Form.Item>
                        )}
                      </div>
                    </div>)}
                  </Form.Item>
                </div>
              </div>
            </div>
            <OperateModal
              visible={isSkillModalVisible}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onOk={(newSelectedSkills) => {
                setSelectedSkills(newSelectedSkills);
                setIsSkillModalVisible(false);
              }}
              onCancel={() => setIsSkillModalVisible(false)}
              items={skills}
              selectedItems={selectedSkills}
              title={t('studio.settings.selectSkills')}
              showEmptyPlaceholder={skills.length === 0}
            />
          </div>
          {showCustomChat && (
            <div className="w-1/2 pl-4 h-[calc(100vh-230px)]">
              <CustomChat handleSendMessage={handleSendMessage} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default StudioSettingsPage;
