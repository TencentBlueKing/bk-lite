'use client';

import React, { useState, useEffect } from 'react';
import {
  Drawer,
  Form,
  Input,
  Button,
  message,
  Modal,
  Select,
  Avatar,
  Divider,
  Space,
  Spin
} from 'antd';
import {
  UserOutlined,
  SolutionOutlined,
  MailOutlined,
  LockOutlined,
  GlobalOutlined,
  ClockCircleOutlined,
  ApartmentOutlined,
  TeamOutlined
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import useApiClient from '@/utils/request';
import { ZONEINFO_OPTIONS, LOCALE_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import PasswordModal from './passwordModal';
import Icon from '@/components/icon';

interface UserInformationProps {
  visible: boolean;
  onClose: () => void;
}

const UserInformation: React.FC<UserInformationProps> = ({ visible, onClose }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [verifyForm] = Form.useForm();
  const [emailForm] = Form.useForm();
  const { get, post } = useApiClient();
  const { clientData } = useClientData();
  const { refreshUserInfo } = useUserInfoContext();


  // 状态管理
  const [loading, setLoading] = useState(false);
  const [verifyPasswordLoading, setVerifyPasswordLoading] = useState(false);
  const [emailChangeLoading, setEmailChangeLoading] = useState(false);
  const [sendVerifyCodeLoading, setSendVerifyCodeLoading] = useState(false);
  const [verifyIdentityModalVisible, setVerifyIdentityModalVisible] = useState(false);
  const [emailModalVisible, setEmailModalVisible] = useState(false);
  const [passwordModalVisible, setPasswordModalVisible] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [userInfo, setUserInfo] = useState<any>({});
  const [hashedCode, setHashedCode] = useState<string>('');
  const [verifyPasswordFor, setVerifyPasswordFor] = useState<'email' | 'password'>('email');
  const [verifyCodeAttempts, setVerifyCodeAttempts] = useState(0);
  const MAX_VERIFY_ATTEMPTS = 10;

  // 获取用户信息
  useEffect(() => {
    if (visible) {
      fetchUserInfo();
    }
  }, [visible]);

  const appIconMap = new Map(
    clientData
      .filter(item => item.icon)
      .map((item) => [item.display_name, item.icon as string])
  );
  const fetchUserInfo = async () => {
    try {
      setLoading(true);
      const data = await get('/console_mgmt/get_user_info/');
      setUserInfo(data || {});
      form.setFieldsValue({
        username: data.username,
        display_name: data.display_name,
        email: data.email,
        timezone: data.timezone,
        locale: data.locale
      });
    } catch (error) {
      console.error('Failed to fetch user info:', error);
    } finally {
      setLoading(false);
    }
  };

  // 保存基本信息
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await post('/console_mgmt/update_user_base_info/', {
        email: userInfo.email,
        display_name: values.display_name,
        timezone: values.timezone,
        locale: values.locale
      });
      message.success(t('common.saveSuccess'));
      // 刷新右上角用户信息
      await refreshUserInfo();
      onClose();
    } catch {
      console.error('Failed to save user info');
    } finally {
      setLoading(false);
    }
  };

  // 验证密码
  const handleVerifyPassword = async (values: any) => {
    try {
      setVerifyPasswordLoading(true);
      await get(`/console_mgmt/validate_pwd/?password=${values.password}`);
      setVerifyIdentityModalVisible(false);
      verifyForm.resetFields();

      // 根据验证目的跳转到对应弹窗
      if (verifyPasswordFor === 'email') {
        setEmailModalVisible(true);
      } else {
        setPasswordModalVisible(true);
      }
    } catch {
      message.error(t('userInfo.passwordError'));
    } finally {
      setVerifyPasswordLoading(false);
    }
  };

  // 发送验证码
  const handleSendVerificationCode = async (email: string) => {
    try {
      setSendVerifyCodeLoading(true);
      const data = await post('/console_mgmt/send_email_code/', { email });
      setSendVerifyCodeLoading(false);
      if (data?.hashed_code) {
        setHashedCode(data.hashed_code);
      }
      message.success(t('userInfo.verificationCodeSent'));
      setCountdown(90);
      setVerifyCodeAttempts(0);
    } catch {
      console.error('Failed to send verification code');
      setSendVerifyCodeLoading(false);
    }
  };

  // 倒计时效果
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // 修改邮箱
  const handleEmailChange = async (values: any) => {
    try {
      setEmailChangeLoading(true);
      await post('/console_mgmt/validate_email_code/', {
        hashed_code: hashedCode,
        input_code: values.verificationCode
      });
      setUserInfo((pre: any) => ({
        ...pre,
        email: values.email
      }));
      message.success(t('userInfo.verifyCodeSuccess'));
      handleEmailClose();
    } catch {
      // 验证失败，增加尝试次数
      const newAttempts = verifyCodeAttempts + 1;
      setVerifyCodeAttempts(newAttempts);

      if (newAttempts >= MAX_VERIFY_ATTEMPTS) {
        message.error(t('userInfo.verificationFailedMaxAttempts'));
        handleEmailClose();
      }
    } finally {
      setEmailChangeLoading(false);
    }
  };

  const handleEmailClose = () => {
    setEmailModalVisible(false);
    emailForm.resetFields();
    setCountdown(0);
    setHashedCode('');
    setVerifyCodeAttempts(0);
  }

  return (
    <>
      <Drawer
        title={t('common.userInfo')}
        placement="right"
        width={700}
        open={visible}
        onClose={onClose}
        maskClosable={false}
        footer={
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button key="cancel" onClick={onClose}>{t('common.cancel')}</Button>
              <Button key="submit" type="primary" onClick={handleSave} loading={loading}>
                {t('common.save')}
              </Button>
            </Space>
          </div>
        }
      >
        <Spin spinning={loading}>
          <div className="space-y-6">
            {/* 基础信息 */}
            <div className="border rounded-xl px-4 pt-4 shadow-lg">
              <h3
                className="text-base font-medium relative pl-3 before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-1 before:h-4 before:bg-blue-500 before:rounded-full">
                {t('userInfo.basicInfo')}
              </h3>
              <div className="flex gap-6 p-4">
                <div className="flex-1">
                  <Form form={form} labelAlign='left' colon={false} requiredMark={false}>
                    <Form.Item
                      label={
                        <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <UserOutlined />
                          <span>{t('userInfo.username')}</span>
                        </div>
                      }
                    >
                      <span className="text-base">{userInfo.username || '-'}</span>
                    </Form.Item>

                    <Form.Item
                      label={
                        <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <SolutionOutlined />
                          <span>{t('userInfo.name')}</span>
                        </div>
                      }
                      name="display_name"
                      rules={[{ required: true, message: t('common.inputRequired') }]}
                    >
                      <Input placeholder={t('userInfo.enterName')} />
                    </Form.Item>

                    <Form.Item
                      label={
                        <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <MailOutlined />
                          <span>{t('userInfo.email')}</span>
                        </div>
                      }
                    >
                      <div className="flex items-center gap-3">
                        <div className="text-base">{userInfo.email || '-'}</div>
                        <Button
                          type="link"
                          size="small"
                          className="p-0 h-auto"
                          onClick={() => {
                            setVerifyPasswordFor('email');
                            setVerifyIdentityModalVisible(true);
                          }}
                        >
                          {t('userInfo.changeEmail')}
                        </Button>
                      </div>
                    </Form.Item>

                    <Form.Item
                      label={
                        <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <LockOutlined />
                          <span>{t('userInfo.password')}</span>
                        </div>
                      }
                    >
                      <div className="flex items-center gap-3">
                        <div className="text-base">********</div>
                        <Button
                          type="link"
                          size="small"
                          className="p-0 h-auto"
                          onClick={() => {
                            setVerifyPasswordFor('password');
                            setVerifyIdentityModalVisible(true);
                          }}
                        >
                          {t('userInfo.changePassword')}
                        </Button>
                      </div>
                    </Form.Item>
                  </Form>
                </div>

                {/* 头像区域 */}
                <div className="flex flex-col items-center">
                  <Avatar
                    size={120}
                    src={userInfo.avatar_url}
                    icon={!userInfo.avatar_url && <UserOutlined />}
                    style={{ backgroundColor: 'var(--color-primary)' }}
                  />
                </div>
              </div>
            </div>

            {/* 时区与语言 */}
            <div className="border rounded-xl px-4 pt-4 shadow-lg">
              <h3 className="text-base font-medium relative pl-3 before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-1 before:h-4 before:bg-blue-500 before:rounded-full">
                {t('userInfo.timezoneAndLanguage')}
              </h3>
              <div className="p-4">
                <Form form={form} labelAlign='left' colon={false}>
                  <Form.Item
                    label={
                      <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <ClockCircleOutlined />
                        <span>{t('userInfo.timezone')}</span>
                      </div>
                    }
                    name="timezone"
                  >
                    <Select showSearch placeholder={`${t('common.selectMsg')}`}>
                      {ZONEINFO_OPTIONS.map(option => (
                        <Select.Option key={option.value} value={option.value}>
                          {t(option.label)}
                        </Select.Option>
                      ))}
                    </Select>
                  </Form.Item>

                  <Form.Item
                    label={
                      <div style={{ minWidth: '80px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <GlobalOutlined />
                        <span>{t('userInfo.language')}</span>
                      </div>
                    }
                    name="locale"
                  >
                    <Select placeholder={`${t('common.selectMsg')}`}>
                      {LOCALE_OPTIONS.map(option => (
                        <Select.Option key={option.value} value={option.value}>
                          {t(option.label)}
                        </Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Form>
              </div>
            </div>

            {/* 组织架构 */}
            <div className="border rounded-xl p-4 shadow-lg">
              <h3 className="text-base font-medium relative pl-3 before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-1 before:h-4 before:bg-blue-500 before:rounded-full">
                {t('userInfo.organization')}
              </h3>
              <Divider />
              <div className="p-4 pt-0">
                <div className="flex gap-1 mb-3">
                  <ApartmentOutlined />{t('userInfo.currentGroup')}
                </div>
                <div className="flex flex-wrap gap-4">
                  {userInfo.group_list && userInfo.group_list.length > 0 ? (
                    userInfo.group_list.map((group: string, index: number) => (
                      <div
                        key={index}
                        className="px-3 py-1.5 border rounded-md bg-[var(--color-fill-1)]"
                      >
                        {group}
                      </div>
                    ))
                  ) : (
                    <span className="text-gray-400">{t('common.noData')}</span>
                  )}
                </div>
              </div>
            </div>

            {/* 角色权限 */}
            <div className="border rounded-xl px-4 pt-4 shadow-lg">
              <h3 className="text-base font-medium relative pl-3 before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-1 before:h-4 before:bg-blue-500 before:rounded-full">
                {t('userInfo.roles')}
              </h3>
              <Divider />
              <div className="p-4 pt-0">
                <div className="flex gap-1 mb-3">
                  <TeamOutlined />
                  {t('userInfo.appPermissions')}
                </div>
                <div className="flex flex-wrap gap-4">
                  {userInfo.role_list && userInfo.role_list.length > 0 ? (
                    (() => {
                      const superAdmin = userInfo.role_list.find((role: any) => !role.app && role.name === 'admin');

                      // 过滤掉超级管理员，其他角色按应用分组
                      const normalRoles = userInfo.role_list.filter((role: any) => !((!role.app) && role.name === 'admin'));
                      const groupedRoles = normalRoles.reduce((acc: any, role: any) => {
                        const appName = role.app_display_name || 'other';
                        if (!acc[appName]) {
                          acc[appName] = [];
                        }
                        acc[appName].push(role);
                        return acc;
                      }, {});

                      // 为每个应用分配颜色
                      const appColors: { [key: string]: string } = {};
                      const colorList = ['blue', 'green', 'orange', 'purple', 'cyan'];
                      Object.keys(groupedRoles).forEach((app, index) => {
                        appColors[app] = colorList[index % colorList.length];
                      });

                      return (
                        <>
                          {/* 超级管理员特殊展示 */}
                          {superAdmin && (
                            <div className="rounded-lg p-3 min-w-[180px]"
                              style={{
                                border: '1px solid var(--color-border)',
                                borderLeft: '3px solid red'
                              }}>
                              <div className="font-medium text-sm">{t('userInfo.superAdmin')}</div>
                              <hr className='mt-1 mb-2 border-t border-[var(--color-border)]' />
                              <div className="flex flex-wrap gap-2">
                                <span className="px-2 py-0.5 rounded text-xs bg-red-50 text-red-600">
                                  {t('userInfo.fullPermissions')}
                                </span>
                              </div>
                            </div>
                          )}
                          {/* 普通应用角色 */}
                          {Object.entries(groupedRoles).map(([app, roles]: [string, any]) => {
                            const color = appColors[app];
                            const borderColor = {
                              blue: '#60a5fa',
                              green: '#22c55e',
                              orange: '#fb923c',
                              purple: '#a78bfa',
                              cyan: '#22d3ee'
                            }[color] || 'var(--color-border)';
                            const tagBgClass = {
                              blue: 'bg-blue-50 text-blue-600',
                              green: 'bg-green-50 text-green-600',
                              orange: 'bg-orange-50 text-orange-600',
                              purple: 'bg-purple-50 text-purple-600',
                              cyan: 'bg-cyan-50 text-cyan-600'
                            }[color] || 'bg-gray-50 text-gray-600';

                            return (
                              <div
                                key={app}
                                className="rounded-lg p-3 min-w-[180px]"
                                style={{
                                  border: '1px solid var(--color-border)',
                                  borderLeft: `3px solid ${borderColor}`
                                }}
                              >
                                <div className="flex items-center gap-2">
                                  {appIconMap.get(app) && (
                                    <Icon type={appIconMap.get(app) || app} className="text-base" />
                                  )}
                                  <span className="font-medium text-sm">{app}</span>
                                </div>
                                <hr className='mt-1 mb-2 border-t border-[var(--color-border)]' />
                                <div className="flex flex-wrap gap-2">
                                  {roles.map((role: any, idx: number) => (
                                    <span
                                      key={idx}
                                      className={`px-2 py-0.5 rounded text-xs ${tagBgClass}`}
                                    >
                                      {role.name}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </>
                      );
                    })()
                  ) : (
                    <span className="text-gray-400">{t('common.noData')}</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Spin>
      </Drawer>

      {/* 验证身份弹窗 */}
      <Modal
        maskClosable={false}
        centered
        title={t('userInfo.verifyIdentity')}
        open={verifyIdentityModalVisible}
        onCancel={() => {
          setVerifyIdentityModalVisible(false);
          verifyForm.resetFields();
        }}
        footer={null}
      >
        <Spin spinning={verifyPasswordLoading}>
          <Form
            form={verifyForm}
            layout="vertical"
            onFinish={handleVerifyPassword}
          >
            <Form.Item
              label={t('userInfo.enterPasswordToVerify')}
              name="password"
              rules={[{ required: true, message: t('common.inputPassword') }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t('common.inputPassword')}
                autoComplete="verification-password"
              />
            </Form.Item>

            <Form.Item className="mb-0">
              <div className="flex justify-end gap-2">
                <Button onClick={() => {
                  setVerifyIdentityModalVisible(false);
                  verifyForm.resetFields();
                }}>
                  {t('common.cancel')}
                </Button>
                <Button type="primary" htmlType="submit">
                  {t('common.next')}
                </Button>
              </div>
            </Form.Item>
          </Form>
        </Spin>

      </Modal>

      {/* 修改邮箱弹窗 */}
      <Modal
        maskClosable={false}
        centered
        title={t('userInfo.changeEmail')}
        open={emailModalVisible}
        onCancel={handleEmailClose}
        footer={null}
      >
        <Spin spinning={emailChangeLoading}>
          <Form
            form={emailForm}
            layout="vertical"
            onFinish={handleEmailChange}
          >
            <Form.Item
              label={t('userInfo.newEmail')}
              name="email"
              rules={[
                { required: true, message: t('userInfo.pleaseEnterEmail') },
                {
                  pattern: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/,
                  message: t('userInfo.emailFormatError')
                }
              ]}
            >
              <Input
                placeholder={t('userInfo.enterNewEmail')}
              />
            </Form.Item>

            <Form.Item
              label={t('userInfo.verificationCode')}
              name="verificationCode"
              rules={[{ required: true, message: t('userInfo.pleaseEnterVerificationCode') }]}
              help={verifyCodeAttempts > 0 && verifyCodeAttempts < MAX_VERIFY_ATTEMPTS ? (
                <span className="text-orange-500">
                  {t('userInfo.attemptsRemaining').replace('{remaining}', String(MAX_VERIFY_ATTEMPTS - verifyCodeAttempts))}
                </span>
              ) : null}
            >
              <div className="flex gap-2">
                <Input
                  placeholder={t('userInfo.enterVerificationCode')}
                  disabled={verifyCodeAttempts >= MAX_VERIFY_ATTEMPTS}
                  maxLength={6}
                />
                <Button
                  type="primary"
                  loading={sendVerifyCodeLoading}
                  onClick={() => {
                    const email = emailForm.getFieldValue('email');
                    if (email) {
                      emailForm.validateFields(['email']).then(() => {
                        handleSendVerificationCode(email);
                      }).catch(() => { });
                    } else {
                      message.error(t('userInfo.pleaseEnterEmail'));
                    }
                  }}
                  disabled={countdown > 0}
                  style={{ minWidth: '100px' }}
                >
                  {countdown > 0 ? `${countdown}s` : t('userInfo.sendCode')}
                </Button>
              </div>
            </Form.Item>

            <Form.Item className="mb-0">
              <div className="flex justify-end gap-2">
                <Button onClick={handleEmailClose} disabled={emailChangeLoading}>
                  {t('common.cancel')}
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={emailChangeLoading}
                  disabled={verifyCodeAttempts >= MAX_VERIFY_ATTEMPTS}
                >
                  {t('common.confirm')}
                </Button>
              </div>
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      {/* 修改密码弹窗 */}
      <PasswordModal
        visible={passwordModalVisible}
        onCancel={() => setPasswordModalVisible(false)}
        onSuccess={() => {
          setPasswordModalVisible(false);
        }}
      />
    </>
  );
};

export default UserInformation;
