import React, { useMemo } from 'react';
import { Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import type { Recipients } from '@/app/cmdb/types/subscription';

interface RecipientSelectorProps {
  value: Recipients;
  onChange: (value: Recipients) => void;
}

const RecipientSelector: React.FC<RecipientSelectorProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const common = useCommon();

  const userOptions = useMemo(
    () =>
      (common?.userList || []).map((u) => ({
        label: `${u.display_name || u.username}(${u.username})`,
        value: Number(u.id),
      })),
    [common?.userList]
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
