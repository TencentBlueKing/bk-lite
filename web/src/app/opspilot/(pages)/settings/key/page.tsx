'use client';
import React, { useState, useEffect } from 'react';
import { Button, Table, Space, Popconfirm, message, Tooltip, Spin } from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import { useSettingsApi } from '@/app/opspilot/api/settings';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import Cookies from 'js-cookie';

interface TableData {
  id: number;
  api_secret: string;
  created_at: string;
  team: string;
  team_name?: string;
}

const initialDataSource: Array<TableData> = [];

const ScrectKeyPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchUserApiSecrets, fetchTeams, deleteUserApiSecret, createUserApiSecret } = useSettingsApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [dataSource, setDataSource] = useState(initialDataSource);
  const [loading, setLoading] = useState<boolean>(false);
  const [creating, setCreating] = useState<boolean>(false);
  const [groups, setGroups] = useState<{ id: string; name: string }[]>([]);
  const [currentTeam, setCurrentTeam] = useState<string | null>(Cookies.get('current_team') || null);

  const fetchData = async (groups: any[]) => {
    setLoading(true);
    try {
      const data = await fetchUserApiSecrets();
      setDataSource(data.map((item: TableData) => ({
        id: item.id,
        api_secret: item.api_secret,
        created_at: item.created_at,
        team: item.team,
        team_name: groups.find(group => group.id === item.team)?.name,
      })));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchGroups = async () => {
    setLoading(true);
    try {
      const data = await fetchTeams();
      setGroups(data);
      return data;
    } catch {
      message.error(t('common.fetchFailed'));
      return [];
    }
  };

  useEffect(() => {
    fetchGroups().then((groupData) => fetchData(groupData));
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
      fetchData(groups);
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

  const handleCopy = (key: string) => {
    navigator.clipboard.writeText(key);
    message.success(t('settings.secret.copied'));
  };

  const handleCreate = async () => {
    setCreating(true);

    try {
      await createUserApiSecret();
      message.success(t('common.addSuccess'));
      fetchData(groups);
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setCreating(false);
    }
  };

  const columns = [
    {
      title: t('settings.secret.key'),
      dataIndex: 'api_secret',
      key: 'api_secret',
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
      title: t('settings.secret.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (text: string) => convertToLocalizedTime(text)
    },
    {
      title: t('settings.secret.group'),
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
          <Button
            type="text"
            icon={<CopyOutlined />}
            onClick={() => handleCopy(record.api_secret)}
          ></Button>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('settings.secret.deleteConfirm')}
              onConfirm={() => handleDelete(record.id)}
              okText="Yes"
              cancelText="No"
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
          title={t('settings.secret.title')}
          content={t('settings.secret.content')}
        />
      </div>
      <section
        className="bg-[var(--color-bg)] p-4 rounded-md"
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
                  {t('settings.secret.create')}
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
    </div>
  );
};

export default ScrectKeyPage;
