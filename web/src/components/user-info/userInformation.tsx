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
  Tag,
  Tooltip,
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
import useApiClient from '@/utils/request';
import { ZONEINFO_OPTIONS, LOCALE_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import PasswordModal from './passwordModal';
import Icon from '@/components/icon';

interface UserInformationProps {
    visible: boolean;
    onClose: () => void;
}

// 预定义的标签颜色
const TAG_COLORS = [
  'magenta', 'red', 'volcano', 'orange', 'gold',
  'lime', 'green', 'cyan', 'blue', 'geekblue', 'purple'
];

const UserInformation: React.FC<UserInformationProps> = ({ visible, onClose }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [verifyForm] = Form.useForm();
  const [emailForm] = Form.useForm();
  const { get, post } = useApiClient();
  const { clientData } = useClientData();


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
      .map((item) => [item.name, item.icon as string])
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

  // 获取随机标签颜色
  const getTagColor = (index: number) => {
    return TAG_COLORS[index % TAG_COLORS.length];
  };

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
            <div>
              <h3 className="text-base font-medium mb-4">{t('userInfo.basicInfo')}</h3>
              <div className={'flex gap-6 p-4 rounded-md bg-[var(--color-fill-1)]'}>
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

            <Divider />

            {/* 时区与语言 */}
            <div>
              <h3 className="text-base font-medium mb-4">{t('userInfo.timezoneAndLanguage')}</h3>
              <div className={'p-4 rounded-md bg-[var(--color-fill-1)]'}>
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

            <Divider />

            {/* 组织架构 */}
            <div>
              <h3 className="text-base font-medium mb-4">{t('userInfo.organization')}</h3>
              <div className={'space-y-4 p-4 rounded-md bg-[var(--color-fill-1)]'}>
                <div>
                  <div className="flex gap-1 mb-2">
                    <ApartmentOutlined />
                    {t('userInfo.currentGroup')}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {userInfo.group_list && userInfo.group_list.length > 0 ? (
                      userInfo.group_list.map((group: string, index: number) => (
                        <Tag
                          key={index}
                          color={getTagColor(index)}
                          className="px-3 py-1"
                        >
                          {group}
                        </Tag>
                      ))
                    ) : (
                      <span className="text-gray-400">{t('common.noData')}</span>
                    )}
                  </div>
                </div>

                <div>
                  <div className="flex gap-1 mb-2">
                    <TeamOutlined />
                    {t('userInfo.roles')}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {userInfo.role_list && userInfo.role_list.length > 0 ? (
                      userInfo.role_list.map((role: any, index: number) => (
                        <div key={index} className="flex items-center justify-center gap-1 rounded-xl border px-3 py-1">
                          {appIconMap.get(role.app) && (
                            <Tooltip title={role.app} placement="top">
                              <div>
                                <Icon type={appIconMap.get(role.app) || role.app} className="w-4 h-4" />
                              </div>
                            </Tooltip>
                          )}
                          <span className="text-xs text-blue-600">
                            {role.name}
                          </span>
                        </div>
                      ))
                    ) : (
                      <span className="text-gray-400">{t('common.noData')}</span>
                    )}
                  </div>
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
