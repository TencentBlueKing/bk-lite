'use client';

import React, { useState, useEffect } from 'react';
import styles from './match.module.scss';
import { SourceItem } from '@/app/alarm/types/integration';
import { useSourceApi } from '@/app/alarm/api/integration';
import { useTranslation } from '@/utils/i18n';
import { Select, Button, Input } from 'antd';
import { PlusCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/alarm/context/common';
import {
  ruleList,
  initialConditionLists,
} from '@/app/alarm/constants/settings';

const { Option } = Select;

interface PolicyItem {
  key: string | undefined;
  operator: string | undefined;
  value: string | undefined;
}

interface MatchRuleProps {
  value?: PolicyItem[][];
  onChange?: (val: PolicyItem[][]) => void;
}

const RulesMatch: React.FC<MatchRuleProps> = ({ value, onChange }) => {
  const { getAlertSources } = useSourceApi();
  const { levelListEvent } = useCommon();
  const { t } = useTranslation();
  const [sourceList, setSourceList] = useState<SourceItem[]>([]);
  const [sourceLoading, setSourceLoading] = useState<boolean>(false);
  const [policyList, setPolicyList] = useState<PolicyItem[][]>(
    value || [
      [
        {
          key: undefined,
          operator: undefined,
          value: undefined,
        },
      ],
    ]
  );
  const policyItem: PolicyItem[] = [
    {
      key: undefined,
      operator: undefined,
      value: undefined,
    },
  ];

  useEffect(() => {
    if (value?.length) {
      setPolicyList(value);
    } else {
      setPolicyList([
        [
          {
            key: undefined,
            operator: undefined,
            value: undefined,
          },
        ],
      ]);
    }
  }, [value]);

  useEffect(() => {
    fetchAlarmSource();
  }, []);

  const changeSelect = async (val: string, index: number, ind: number) => {
    const updatedPolicyList = [...policyList];
    const item = updatedPolicyList[index][ind];
    item.key = val;
    item.operator = undefined;
    item.value = undefined;
    setPolicyList(updatedPolicyList);
    onChange?.(updatedPolicyList);
  };

  const addOr = () => {
    const updated = [...policyList, JSON.parse(JSON.stringify(policyItem))];
    setPolicyList(updated);
    onChange?.(updated);
  };

  const deleteOr = (index: number) => {
    const updated = [...policyList];
    updated.splice(index, 1);
    setPolicyList(updated);
    onChange?.(updated);
  };

  const addAnd = (index: number) => {
    const updated = [...policyList];
    updated[index].push({ ...policyItem[0] });
    setPolicyList(updated);
    onChange?.(updated);
  };

  const deleteAnd = (index: number, ind: number) => {
    const updated = [...policyList];
    updated[index].splice(ind, 1);
    setPolicyList(updated);
    onChange?.(updated);
  };

  const fetchAlarmSource = async () => {
    setSourceLoading(true);
    try {
      const data: any = await getAlertSources();
      if (data) setSourceList(data);
      else console.error('获取告警源列表失败');
    } finally {
      setSourceLoading(false);
    }
  };

  return (
    <div className="pl-[2px] border-l border-[#c4c6cc] w-full ml-[10px] mb-[2px]">
      {policyList.map?.((orItem, index) => (
        <div key={index} className="relative -left-[15px] pb-[10px]">
          <div className={`absolute text-center ${styles.ruleOr}`}>或</div>
          <div className="bg-[var(--color-bg-4)] ml-[33px] relative top-[15px]">
            <div className="px-[12px] py-[12px] space-y-3">
              {orItem.map((i, ind) => (
                <div key={ind} className="relative">
                  <div className={`ml-[8px] flex items-center`}>
                    <div className={styles.ruleAnd}>且</div>
                    <div className={`${styles.ruleItem} mr-[4px]`}>
                      <div className={styles.keySelect}>
                        <Select
                          allowClear
                          value={i.key}
                          placeholder={`${t('common.selectTip')}`}
                          onChange={(value) => changeSelect(value, index, ind)}
                        >
                          {ruleList.map((item) => (
                            <Option key={item.name} value={item.name}>
                              {item.verbose_name}
                            </Option>
                          ))}
                        </Select>
                      </div>
                      <div className={styles.condSelect}>
                        <Select
                          allowClear
                          value={i.operator}
                          placeholder={`${t('common.selectTip')}`}
                          onChange={(value) => {
                            const updatedPolicyList = [...policyList];
                            updatedPolicyList[index][ind].operator = value;
                            setPolicyList(updatedPolicyList);
                            onChange?.(updatedPolicyList);
                          }}
                        >
                          {(initialConditionLists[i.key as string] || []).map(
                            (item) => (
                              <Option key={item.name} value={item.name}>
                                {item.desc}
                              </Option>
                            ),
                          )}
                        </Select>
                      </div>
                      <div className={styles.valueInput}>
                        {['level', 'source_id'].includes(i.key as string) ? (
                          <Select
                            value={i.value}
                            showSearch
                            loading={i.key === 'source_id' && sourceLoading}
                            placeholder={`${t('common.selectTip')}`}
                            onChange={(value) => {
                              const updatedPolicyList = [...policyList];
                              updatedPolicyList[index][ind].value = value;
                              setPolicyList(updatedPolicyList);
                              onChange?.(updatedPolicyList);
                            }}
                          >
                            {i.key === 'level' &&
                              levelListEvent.map(
                                ({ level_id, level_display_name }) => (
                                  <Option key={level_id} value={level_id}>
                                    {level_display_name}
                                  </Option>
                                ),
                              )}
                            {i.key === 'source_id' &&
                              sourceList.map((source) => (
                                <Option key={source.id} value={source.id}>
                                  {source.name}
                                </Option>
                              ))}
                          </Select>
                        ) : (
                          <Input
                            value={i.value}
                            placeholder={t('common.inputTip')}
                            onChange={(e) => {
                              const updatedPolicyList = [...policyList];
                              updatedPolicyList[index][ind].value =
                                e.target.value;
                              setPolicyList(updatedPolicyList);
                              onChange?.(updatedPolicyList);
                            }}
                          />
                        )}
                      </div>
                      <span className={styles.action}>
                        <PlusCircleOutlined
                          title="新增"
                          onClick={() => addAnd(index)}
                        />
                      </span>
                      <span className={styles.action}>
                        {orItem.length > 1 && (
                          <MinusCircleOutlined
                            title="删除"
                            onClick={() => deleteAnd(index, ind)}
                          />
                        )}
                      </span>
                    </div>

                    {ind > 0 && (
                      <div className="absolute left-[12px] -top-[20px] h-[25px] border-l border-[#c4c6cc]"></div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <span
            className={`${styles.action} absolute right-[-5px] top-[6px] z-10`}
          >
            {policyList.length > 1 && (
              <MinusCircleOutlined onClick={() => deleteOr(index)} />
            )}
          </span>
        </div>
      ))}
      <div className="relative -left-[15px] transform translate-y-[5px]">
        <Button onClick={addOr} size="small" className="add-button">
          <div className="relative text-[22px] text-[#979BA5] -top-[2px]">
            +
          </div>
        </Button>
      </div>
    </div>
  );
};

export default RulesMatch;
