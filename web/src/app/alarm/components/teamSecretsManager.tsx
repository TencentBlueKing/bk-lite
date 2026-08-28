'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, message, Popconfirm, Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { PlusOutlined, ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { useSourceApi } from '@/app/alarm/api/integration';
import { TeamSecretItem } from '@/app/alarm/types/integration';
import GroupTreeSelect from '@/components/group-tree-select';
import SecretValueDisplay from '@/components/secret-value-display';

interface TeamSecretsManagerProps {
  sourceId: number | string;
}

const TeamSecretsManager: React.FC<TeamSecretsManagerProps> = ({ sourceId }) => {
  const { t } = useTranslation();
  const { flatGroups } = useUserInfoContext();
  const { listTeamSecrets, addTeamSecret, revealTeamSecret, regenerateTeamSecret, removeTeamSecret } = useSourceApi();

  const [loading, setLoading] = useState(false);
  const [teamSecrets, setTeamSecrets] = useState<TeamSecretItem[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<number | undefined>();
  const [addingSecret, setAddingSecret] = useState(false);
  const [regeneratingTeamId, setRegeneratingTeamId] = useState<string | null>(null);
  const [revealingTeamId, setRevealingTeamId] = useState<string | null>(null);
  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, string>>({});

  const fetchTeamSecrets = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listTeamSecrets(sourceId);
      setTeamSecrets(Array.isArray(res) ? res : res.team_secrets || []);
    } catch (error) {
      console.error('Failed to fetch team secrets:', error);
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => {
    setSelectedTeamId(undefined);
    setRevealedSecrets({});
    fetchTeamSecrets();
  }, [fetchTeamSecrets]);

  const handleAddTeamSecret = async () => {
    if (!selectedTeamId) {
      message.warning(t('incidents.teamRequired'));
      return;
    }

    setAddingSecret(true);
    try {
      const result = await addTeamSecret(sourceId, String(selectedTeamId));
      setRevealedSecrets((current) => ({ ...current, [result.team_id]: result.secret }));
      message.success(t('integration.teamSecretAdded'));
      setSelectedTeamId(undefined);
      fetchTeamSecrets();
    } catch (error) {
      console.error('Failed to add team secret:', error);
    } finally {
      setAddingSecret(false);
    }
  };

  const handleRegenerateSecret = async (teamId: string) => {
    setRegeneratingTeamId(teamId);
    try {
      const result = await regenerateTeamSecret(sourceId, teamId);
      setRevealedSecrets((current) => ({ ...current, [result.team_id]: result.secret }));
      message.success(t('integration.teamSecretRegenerated'));
      fetchTeamSecrets();
    } catch (error) {
      console.error('Failed to regenerate team secret:', error);
    } finally {
      setRegeneratingTeamId(null);
    }
  };

  const handleRevealSecret = async (teamId: string) => {
    setRevealingTeamId(teamId);
    try {
      const result = await revealTeamSecret(sourceId, teamId);
      setRevealedSecrets((current) => ({ ...current, [result.team_id]: result.secret }));
    } catch (error) {
      console.error('Failed to reveal team secret:', error);
    } finally {
      setRevealingTeamId(null);
    }
  };

  const handleRemoveTeamSecret = async (teamId: string) => {
    try {
      await removeTeamSecret(sourceId, teamId);
      setRevealedSecrets((current) => {
        const next = { ...current };
        delete next[teamId];
        return next;
      });
      message.success(t('integration.teamSecretRemoved'));
      fetchTeamSecrets();
    } catch (error) {
      console.error('Failed to remove team secret:', error);
    }
  };

  const existingTeamIds = teamSecrets.map(ts => ts.team_id);
  const displayTeamSecrets = teamSecrets.map((teamSecret) => ({
    ...teamSecret,
    team_name: teamSecret.team_name || flatGroups.find(g => String(g.id) === teamSecret.team_id)?.name || teamSecret.team_id,
  }));
  const availableTeamIds = flatGroups
    .filter(g => !existingTeamIds.includes(String(g.id)))
    .map(g => Number(g.id));

  const columns = [
    {
      title: t('incidents.team'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 200,
    },
    {
      title: t('integration.secret'),
      dataIndex: 'secret',
      key: 'secret',
      render: (_: unknown, record: TeamSecretItem) => {
        const secret = revealedSecrets[record.team_id];
        if (secret) return <SecretValueDisplay value={secret} />;
        return (
          <Button
            type="link"
            className="h-auto p-0"
            loading={revealingTeamId === record.team_id}
            onClick={() => handleRevealSecret(record.team_id)}
          >
            {t('common.view')}
          </Button>
        );
      },
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 180,
      render: (_: unknown, record: TeamSecretItem) => (
        <div className="flex items-center gap-2">
          <Button
            type="link"
            size="small"
            icon={<ReloadOutlined spin={regeneratingTeamId === record.team_id} />}
            loading={regeneratingTeamId === record.team_id}
            onClick={() => handleRegenerateSecret(record.team_id)}
          >
            {t('integration.regenerateSecret')}
          </Button>
          <Popconfirm
            title={t('integration.confirmRemoveTeamSecret')}
            onConfirm={() => handleRemoveTeamSecret(record.team_id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('integration.removeTeamSecret')}
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <div className="p-4">
      <div className="mb-4">
        <p className="text-gray-500 mb-4">{t('integration.teamSecretsDesc')}</p>
        <div className="flex items-center gap-4">
          <GroupTreeSelect
            value={selectedTeamId ? [selectedTeamId] : []}
            onChange={(val) => setSelectedTeamId(Array.isArray(val) ? val[0] : val)}
            placeholder={t('incidents.selectTeam')}
            multiple={false}
            mode="ownership"
            style={{ width: 300 }}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={addingSecret}
            disabled={!selectedTeamId || availableTeamIds.length === 0}
            onClick={handleAddTeamSecret}
          >
            {t('integration.addTeamSecret')}
          </Button>
        </div>
      </div>

      <Spin spinning={loading}>
        {teamSecrets.length === 0 && !loading ? (
          <CompactEmptyState description={t('integration.noTeamSecrets')} />
        ) : (
          <Table
            dataSource={displayTeamSecrets}
            columns={columns}
            rowKey="team_id"
            pagination={false}
            size="small"
          />
        )}
      </Spin>
    </div>
  );
};

export default TeamSecretsManager;
