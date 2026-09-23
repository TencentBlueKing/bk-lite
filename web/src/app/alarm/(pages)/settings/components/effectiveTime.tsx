import React, { useEffect } from 'react';
import dayjs from 'dayjs';
import { Select, DatePicker, TimePicker } from 'antd';
import { timeInterval, weekList } from '@/app/alarm/constants/settings';

const { Option } = Select;
const { RangePicker } = DatePicker;

export interface EffectiveTimeValue {
  type: 'one' | 'day' | 'week' | 'month';
  week_month: number[];
  start_time: string;
  end_time: string;
}

interface EffectiveTimeProps {
  open: boolean;
  value?: EffectiveTimeValue;
  onChange?: (val: EffectiveTimeValue) => void;
}

const defaultValue: EffectiveTimeValue = {
  type: 'day',
  week_month: [],
  start_time: '00:00:00',
  end_time: '23:59:59',
};

const EffectiveTime: React.FC<EffectiveTimeProps> = ({
  value,
  onChange,
}) => {
  const form = value || defaultValue;

  useEffect(() => {
    if (!value) {
      onChange?.(defaultValue);
    }
  }, [value, onChange]);

  const triggerChange = (changed: Partial<EffectiveTimeValue>) => {
    onChange?.({ ...form, ...changed });
  };

  const handleTypeChange = (nextType: EffectiveTimeValue['type']) => {
    if (nextType === 'one') {
      triggerChange({
        type: nextType,
        start_time: dayjs().startOf('day').format('YYYY-MM-DD HH:mm:ss'),
        end_time: dayjs()
          .add(1, 'month')
          .endOf('day')
          .format('YYYY-MM-DD HH:mm:ss'),
      });
      return;
    }
    triggerChange({
      type: nextType,
      start_time: '00:00:00',
      end_time: '23:59:59',
    });
  };

  return (
    <div className="flex" id="effective-time">
      <div className="flex-1 mr-[6px]">
        <Select value={form.type} onChange={handleTypeChange}>
          {timeInterval.map((item) => (
            <Option key={item.value} value={item.value}>
              {item.name}
            </Option>
          ))}
        </Select>
      </div>
      <div className="flex-[4] flex">
        {form.type === 'week' && (
          <Select
            mode="multiple"
            maxTagCount={1}
            value={form.week_month}
            onChange={(v) => triggerChange({ week_month: v })}
            className="flex-1"
          >
            {weekList.map((item) => (
              <Option key={item.value} value={item.value}>
                {item.name}
              </Option>
            ))}
          </Select>
        )}
        {form.type === 'month' && (
          <Select
            mode="multiple"
            maxTagCount={2}
            value={form.week_month}
            onChange={(v) => triggerChange({ week_month: v })}
            className="flex-1"
          >
            {[...Array(31)].map((_, i) => (
              <Option key={i + 1} value={i + 1}>
                {i + 1}
              </Option>
            ))}
          </Select>
        )}
        {form.type !== 'one' && (
          <TimePicker.RangePicker
            allowClear={false}
            format="HH:mm:ss"
            className="flex-1 ml-[6px]"
            value={[
              dayjs(form.start_time, 'HH:mm:ss'),
              dayjs(form.end_time, 'HH:mm:ss'),
            ]}
            onChange={(_, dateStrings) =>
              triggerChange({
                start_time: dateStrings[0],
                end_time: dateStrings[1],
              })
            }
          />
        )}
        {form.type === 'one' && (
          <RangePicker
            showTime
            format="YYYY-MM-DD HH:mm:ss"
            allowClear={false}
            className="flex-1 ml-[6px]"
            value={
              form.start_time && form.end_time
                ? [
                  dayjs(form.start_time, 'YYYY-MM-DD HH:mm:ss'),
                  dayjs(form.end_time, 'YYYY-MM-DD HH:mm:ss'),
                ]
                : [dayjs().startOf('day'), dayjs().add(1, 'month').endOf('day')]
            }
            onChange={(_, dateStrings) => {
              if (dateStrings?.length === 2) {
                triggerChange({
                  start_time: dateStrings[0],
                  end_time: dateStrings[1],
                });
              }
            }}
          />
        )}
      </div>
    </div>
  );
};

export default EffectiveTime;

export { defaultValue as defaultEffectiveTime };
