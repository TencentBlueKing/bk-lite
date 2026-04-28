'use client';
import React, { useState, useEffect } from 'react';
import { Button, Table, Space, Popconfirm, message, Tooltip, Spin, Modal, Checkbox, Typography } from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined, WarningOutlined } from '@ant-design/icons';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import { UserApiSecretListItem, useSettingsApi } from '@/app/system-manager/api/settings';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useCopy } from '@/hooks/useCopy';
import Cookies from 'js-cookie';

interface TableData {
  id: number;
  api_secret_preview: string;
  created_at: string;
  team: string;
  team_name?: string;
}

const initialDataSource: Array<TableData> = [];

const ScrectKeyPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchUserApiSecrets, deleteUserApiSecret, createUserApiSecret } = useSettingsApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { copy } = useCopy();
  const [dataSource, setDataSource] = useState(initialDataSource);
  const [loading, setLoading] = useState<boolean>(false);
  const [creating, setCreating] = useState<boolean>(false);
  const [currentTeam, setCurrentTeam] = useState<string | null>(Cookies.get('current_team') || null);
  const [successModalVisible, setSuccessModalVisible] = useState(false);
  const [newSecret, setNewSecret] = useState('');
  const [savedCheckbox, setSavedCheckbox] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchUserApiSecrets();
      setDataSource(data.map((item: UserApiSecretListItem) => ({
        id: item.id,
        api_secret_preview: item.api_secret_preview,
        created_at: item.created_at,
        team: String(item.team),
        team_name: item.team_name,
      })));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const checkCookieChange = setInterval(() => {
      const newCurrentTeam = Cookies.get('current_team');
      if (newCurrentTeam !== currentTeam) {
        setCurrentTeam(newCurrentTeam || null);
      }
    }, 1000);

    return () => clearInterval(checkCookieChange);
  }, [currentTeam]);

  useEffect(() => {
    if (currentTeam !== dataSource?.[0]?.team) {
      fetchData();
    }
  }, [currentTeam]);

  const handleDelete = async (key: number) => {
    try {
      await deleteUserApiSecret(key);
      const newDataSource = dataSource.filter(item => item.id !== key);
      setDataSource(newDataSource);
      message.success(`Deleted key: ${key}`);
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleCreate = async () => {
    setCreating(true);

    try {
      const response = await createUserApiSecret();
      // response could be the newly created object which contains api_secret
      setNewSecret(response?.api_secret || '');
      setSavedCheckbox(false);
      setSuccessModalVisible(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.saveFailed'));
    } finally {
      setCreating(false);
    }
  };

  const handleCloseModal = () => {
    setSuccessModalVisible(false);
    setNewSecret('');
    setSavedCheckbox(false);
    fetchData();
  };

  const columns = [
    {
      title: t('system.settings.secret.key'),
      dataIndex: 'api_secret_preview',
      key: 'api_secret_preview',
      ellipsis: {
        showTitle: false,
      },
      render: (secret: string) => (
        <Tooltip placement="topLeft" title={secret}>
          {secret}
        </Tooltip>
      ),
      width: 200,
    },
    {
      title: t('system.settings.secret.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (text: string) => convertToLocalizedTime(text)
    },
    {
      title: t('system.settings.secret.group'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 150,
    },
    {
      title: '',
      key: 'action',
      width: 80,
      render: (_: unknown, record: TableData) => (
        <Space size={0}>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('system.settings.secret.deleteConfirm')}
              onConfirm={() => handleDelete(record.id)}
              okText={t('common.yes')}
              cancelText={t('common.no')}
            >
              <Button type="text" icon={<DeleteOutlined />} danger></Button>
            </Popconfirm>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4">
        <TopSection
          title={t('system.settings.secret.title')}
          content={t('system.settings.secret.content')}
        />
      </div>
      <section
        className="rounded-md bg-(--color-bg) p-4"
        style={{ height: 'calc(100vh - 235px)' }}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Spin />
          </div>
        ) : (
          <>
            <div className="flex justify-end mb-4">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleCreate}
                  loading={creating}
                  disabled={creating}
                >
                  {t('system.settings.secret.create')}
                </Button>
              </PermissionWrapper>
            </div>
            <Table
              dataSource={dataSource}
              columns={columns}
              pagination={false}
              rowKey="id"
            />
          </>
        )}
      </section>

      <Modal
        title={t('system.settings.secret.createSuccessTitle')}
        open={successModalVisible}
        closable={false}
        maskClosable={false}
        footer={[
          <Checkbox
            key="checked"
            className='float-start py-1 text-(--color-text-1)'
            checked={savedCheckbox}
            onChange={(e) => setSavedCheckbox(e.target.checked)}
          >
            {t('system.settings.secret.confirmSave')}
          </Checkbox>,
          <Button
            key="confirm"
            type="primary"
            disabled={!savedCheckbox}
            onClick={handleCloseModal}
          >
            {t('system.settings.secret.savedAction')}
          </Button>,
        ]}
      >
        <div
          className="mb-2 border p-4"
          style={{
            backgroundColor: 'var(--color-bg-active)',
            borderColor: 'var(--color-border-2)',
            color: 'var(--color-text-2)',
          }}
        >
          <Typography.Text type="warning" className='flex'>
            <WarningOutlined className="mr-2 mt-1 items-start text-base" />
            <span>
              {t('system.settings.secret.createSuccessDesc')}
            </span>
          </Typography.Text>
        </div>

        <div className="mb-6">
          <div className="flex items-center gap-2">
            <div
              className="flex-1 break-all border p-2 font-mono"
              style={{
                backgroundColor: 'var(--color-fill-1)',
                borderColor: 'var(--color-border-2)',
                color: 'var(--color-text-1)',
              }}
            >
              <Typography.Text strong className="whitespace-nowrap mr-1">
                {t('system.settings.secret.key')}:
              </Typography.Text>
              {newSecret}
            </div>
          </div>
          <div className="mt-1 flex justify-start">
            <Button
              type="link"
              size="small"
              className='text-xs'
              icon={<CopyOutlined />}
              onClick={() => copy(newSecret)}
            >
              {t('common.copy')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ScrectKeyPage;
