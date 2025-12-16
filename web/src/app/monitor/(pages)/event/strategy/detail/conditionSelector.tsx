import React, { useState } from 'react';
import { Select, Input, Button } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ListItem, MetricItem } from '@/app/monitor/types';
import strategyStyle from '../index.module.scss';
import { useConditionList } from '@/app/monitor/hooks';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';

const { Option } = Select;
const defaultGroup = ['instance_id'];

interface FilterItem {
  name: string | null;
  method: string | null;
  value: string;
}

interface ConditionData {
  metric: string | null;
  filters: FilterItem[];
  group: string[];
}

interface ConditionSelectorProps {
  data: ConditionData;
  metricData: any[];
  labels: string[];
  loading?: boolean;
  monitorName: string;
  onMetricChange: (value: string) => void;
  onFiltersChange: (filters: FilterItem[]) => void;
  onGroupChange: (group: string[]) => void;
}

const ConditionSelector: React.FC<ConditionSelectorProps> = ({
  data,
  metricData,
  labels,
  loading,
  monitorName,
  onMetricChange,
  onFiltersChange,
  onGroupChange,
}) => {
  const { t } = useTranslation();
  const CONDITION_LIST = useConditionList();
  const { getGroupIds } = useObjectConfigInfo();
  const [conditions, setConditions] = useState<FilterItem[]>(
    data.filters || []
  );

  const handleLabelChange = (value: string, index: number) => {
    const newConditions = [...conditions];
    newConditions[index].name = value;
    setConditions(newConditions);
    onFiltersChange(newConditions);
  };

  const handleConditionChange = (value: string, index: number) => {
    const newConditions = [...conditions];
    newConditions[index].method = value;
    setConditions(newConditions);
    onFiltersChange(newConditions);
  };

  const handleValueChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const newConditions = [...conditions];
    newConditions[index].value = e.target.value;
    setConditions(newConditions);
    onFiltersChange(newConditions);
  };

  const addConditionItem = () => {
    const newConditions = [
      ...conditions,
      { name: null, method: null, value: '' },
    ];
    setConditions(newConditions);
    onFiltersChange(newConditions);
  };

  const deleteConditionItem = (index: number) => {
    const newConditions = conditions.filter((_, i) => i !== index);
    setConditions(newConditions);
    onFiltersChange(newConditions);
  };

  return (
    <div className={strategyStyle.condition}>
      <Select
        allowClear
        style={{
          width: '300px',
          margin: '0 20px 10px 0',
        }}
        placeholder={t('monitor.metric')}
        showSearch
        value={data.metric}
        loading={loading}
        options={metricData.map((item) => ({
          label: item.display_name,
          title: item.name,
          options: (item.child || []).map((tex: MetricItem) => ({
            label: tex.display_name,
            value: tex.name,
          })),
        }))}
        onChange={onMetricChange}
      />

      <div className={strategyStyle.conditionItem}>
        {conditions.length ? (
          <ul className={strategyStyle.conditions}>
            <li className={strategyStyle.conditionTitle}>
              <span>{t('monitor.filter')}</span>
            </li>
            {conditions.map((conditionItem, index) => (
              <li
                className={`${strategyStyle.itemOption} ${strategyStyle.filter}`}
                key={index}
              >
                <Select
                  className={strategyStyle.filterLabel}
                  placeholder={t('monitor.label')}
                  showSearch
                  value={conditionItem.name}
                  onChange={(val) => handleLabelChange(val, index)}
                >
                  {labels.map((item: string) => (
                    <Option value={item} key={item}>
                      {item}
                    </Option>
                  ))}
                </Select>
                <Select
                  style={{ width: '100px' }}
                  placeholder={t('monitor.term')}
                  value={conditionItem.method}
                  onChange={(val) => handleConditionChange(val, index)}
                >
                  {CONDITION_LIST.map((item: ListItem) => (
                    <Option value={item.id} key={item.id}>
                      {item.name}
                    </Option>
                  ))}
                </Select>
                <Input
                  style={{ width: '150px' }}
                  placeholder={t('monitor.value')}
                  value={conditionItem.value}
                  onChange={(e) => handleValueChange(e, index)}
                />
                <Button
                  icon={<CloseOutlined />}
                  onClick={() => deleteConditionItem(index)}
                />
                <Button icon={<PlusOutlined />} onClick={addConditionItem} />
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex items-center mr-[20px]">
            <span className="mr-[10px]">{t('monitor.filter')}</span>
            <Button
              disabled={!data.metric}
              icon={<PlusOutlined />}
              onClick={addConditionItem}
            />
          </div>
        )}
      </div>
      <div>
        <span className="mr-[10px]">{t('common.group')}</span>
        <Select
          style={{
            width: '300px',
            margin: '0 10px 10px 0',
          }}
          showSearch
          allowClear
          mode="multiple"
          maxTagCount="responsive"
          placeholder={t('common.group')}
          value={data.group}
          onChange={onGroupChange}
        >
          {(getGroupIds(monitorName)?.list || defaultGroup).map(
            (item: string) => (
              <Option value={item} key={item}>
                {item}
              </Option>
            )
          )}
        </Select>
      </div>
    </div>
  );
};

export default ConditionSelector;
