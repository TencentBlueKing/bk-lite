'use client';

import React, { useState, useEffect } from 'react';
import styles from './match.module.scss';
import type { SourceItem } from '@/app/alarm/types/integration-guide';
import { useTranslation } from '@/utils/i18n';
import { Select, Input } from 'antd';
import { PlusCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';
import {
  alarmMatchRuleInitialConditionLists as initialConditionLists,
  alarmMatchRuleRuleList as ruleList,
} from '@/app/alarm/constants/alarm-defaults';

const { Option } = Select;

interface PolicyItem {
  key: string | undefined;
  operator: string | undefined;
  value: string | undefined;
}

export interface AlarmMatchRuleProps {
  value?: PolicyItem[][];
  onChange?: (val: PolicyItem[][]) => void;
  ruleOptions?: { name: string; verbose_name: string }[];
  conditionOptions?: Record<string, { name: string; desc: string }[]>;
  levelType?: 'alert' | 'event' | 'incident';
  sourceOptions?: SourceItem[];
  loadSourceOptions?: () => Promise<SourceItem[]>;
  levelOptionsOverride?: Array<{
    level_id: string | number;
    level_display_name: string;
  }>;
}

const AlarmMatchRule: React.FC<AlarmMatchRuleProps> = ({
  value,
  onChange,
  ruleOptions,
  conditionOptions,
  sourceOptions,
  loadSourceOptions,
  levelOptionsOverride,
}) => {
  const { t } = useTranslation();
  const [sourceList, setSourceList] = useState<SourceItem[]>(sourceOptions || []);
  const [sourceLoading, setSourceLoading] = useState<boolean>(false);
  const [policyList, setPolicyList] = useState<PolicyItem[][]>(
    value || [[{ key: undefined, operator: undefined, value: undefined }]],
  );
  const policyItem: PolicyItem[] = [
    {
      key: undefined,
      operator: undefined,
      value: undefined,
    },
  ];
  const levelOptions = levelOptionsOverride || [];

  useEffect(() => {
    if (sourceOptions) {
      setSourceList(sourceOptions);
    }
  }, [sourceOptions]);

  useEffect(() => {
    if (value?.length) {
      setPolicyList(value);
    } else {
      setPolicyList([[{ key: undefined, operator: undefined, value: undefined }]]);
    }
  }, [value]);

  useEffect(() => {
    if (!sourceOptions && loadSourceOptions) {
      void fetchAlarmSource();
    }
  }, [loadSourceOptions, sourceOptions]);

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
    if (!loadSourceOptions) {
      setSourceList([]);
      return;
    }

    setSourceLoading(true);
    try {
      const data: any = await loadSourceOptions();
      if (data) setSourceList(data);
    } finally {
      setSourceLoading(false);
    }
  };

  return (
    <div className="mb-[2px] ml-[10px] w-full border-l border-[#c4c6cc] pl-[2px]">
      {policyList.map?.((orItem, index) => (
        <div key={index} className="relative -left-[15px] pb-[10px]">
          <div className={`absolute text-center ${styles.ruleOr}`}>
            {t('common.or')}
          </div>
          <div className="relative top-[15px] ml-[33px] bg-[var(--color-bg-4)]">
            <div className="space-y-3 px-[12px] py-[12px]">
              {orItem.map((item, ind) => (
                <div key={ind} className="relative">
                  <div className="ml-[8px] flex items-center">
                    <div className={styles.ruleAnd}>{t('common.and')}</div>
                    <div className={`${styles.ruleItem} mr-[4px]`}>
                      <div className={styles.keySelect}>
                        <Select
                          allowClear
                          value={item.key}
                          placeholder={t('common.selectTip')}
                          onChange={(nextValue) =>
                            changeSelect(nextValue, index, ind)
                          }
                        >
                          {(ruleOptions || ruleList).map((rule) => (
                            <Option key={rule.name} value={rule.name}>
                              {rule.verbose_name}
                            </Option>
                          ))}
                        </Select>
                      </div>
                      <div className={styles.condSelect}>
                        <Select
                          allowClear
                          value={item.operator}
                          placeholder={t('common.selectTip')}
                          onChange={(nextValue) => {
                            const updatedPolicyList = [...policyList];
                            updatedPolicyList[index][ind].operator = nextValue;
                            setPolicyList(updatedPolicyList);
                            onChange?.(updatedPolicyList);
                          }}
                        >
                          {(
                            (conditionOptions || initialConditionLists)[
                              item.key as string
                            ] || []
                          ).map((condition) => (
                            <Option key={condition.name} value={condition.name}>
                              {condition.desc}
                            </Option>
                          ))}
                        </Select>
                      </div>
                      <div className={styles.valueInput}>
                        {['level', 'source_id'].includes(item.key as string) ? (
                          <Select
                            value={item.value}
                            showSearch
                            loading={item.key === 'source_id' && sourceLoading}
                            placeholder={t('common.selectTip')}
                            onChange={(nextValue) => {
                              const updatedPolicyList = [...policyList];
                              updatedPolicyList[index][ind].value = nextValue;
                              setPolicyList(updatedPolicyList);
                              onChange?.(updatedPolicyList);
                            }}
                          >
                            {item.key === 'level' &&
                              levelOptions.map(
                                ({ level_id, level_display_name }) => (
                                  <Option key={level_id} value={level_id}>
                                    {level_display_name}
                                  </Option>
                                ),
                              )}
                            {item.key === 'source_id' &&
                              sourceList.map((source) => (
                                <Option key={source.id} value={source.id}>
                                  {source.name}
                                </Option>
                              ))}
                          </Select>
                        ) : (
                          <Input
                            value={item.value}
                            placeholder={t('common.inputTip')}
                            onChange={(event) => {
                              const updatedPolicyList = [...policyList];
                              updatedPolicyList[index][ind].value =
                                event.target.value;
                              setPolicyList(updatedPolicyList);
                              onChange?.(updatedPolicyList);
                            }}
                          />
                        )}
                      </div>
                      <span className={styles.action}>
                        <PlusCircleOutlined
                          title={t('common.addNew')}
                          onClick={() => addAnd(index)}
                        />
                      </span>
                      <span className={styles.action}>
                        {orItem.length > 1 && (
                          <MinusCircleOutlined
                            title={t('common.delete')}
                            onClick={() => deleteAnd(index, ind)}
                          />
                        )}
                      </span>
                    </div>

                    {ind > 0 && (
                      <div className="absolute left-[12px] -top-[20px] h-[25px] border-l border-[#c4c6cc]" />
                    )}
                  </div>
                </div>
              ))}

              <div className="pl-[36px]">
                <a className="text-xs" onClick={() => addAnd(index)}>
                  + {t('common.and')}
                </a>
                {policyList.length > 1 && (
                  <a className="ml-4 text-xs" onClick={() => deleteOr(index)}>
                    - {t('common.or')}
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}

      <div className="pl-[18px]">
        <a className="text-xs" onClick={addOr}>
          + {t('common.or')}
        </a>
      </div>
    </div>
  );
};

export default AlarmMatchRule;
