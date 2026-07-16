import React, { useMemo } from 'react';
import { Select } from 'antd';
import type { CmdbUserSummary } from '@/components/cmdb-shared';
import { useTranslation } from '@/utils/i18n';
import type { Recipients } from './types';

interface RecipientSelectorProps {
  value: Recipients;
  onChange: (value: Recipients) => void;
  userList: CmdbUserSummary[];
}

const RecipientSelector: React.FC<RecipientSelectorProps> = ({
  value,
  onChange,
  userList,
}) => {
  const { t } = useTranslation();

  const userOptions = useMemo(
    () =>
      userList.map((u) => ({
        label: `${u.display_name || u.username}(${u.username})`,
        value: Number(u.id),
      })),
    [userList]
  );

  return (
    <Select
      mode="multiple"
      style={{ width: '100%' }}
      maxTagCount="responsive"
      maxTagTextLength={12}
      placeholder={t('subscription.selectUsers')}
      value={value?.users || []}
      onChange={(users) => onChange({ users })}
      options={userOptions}
    />
  );
};

export default RecipientSelector;
