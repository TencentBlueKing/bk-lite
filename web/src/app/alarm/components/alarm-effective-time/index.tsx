import React, { useEffect, useRef } from 'react';
import dayjs from 'dayjs';
import { Select, DatePicker, TimePicker } from 'antd';
import {
  alarmEffectiveTimeIntervals as timeInterval,
  alarmEffectiveTimeWeekList as weekList,
} from '@/app/alarm/constants/alarm-defaults';

const { Option } = Select;
const { RangePicker } = DatePicker;

export interface EffectiveTimeValue {
  type: 'one' | 'day' | 'week' | 'month';
  week_month: number[];
  start_time: string;
  end_time: string;
}

interface AlarmEffectiveTimeProps {
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

const AlarmEffectiveTime: React.FC<AlarmEffectiveTimeProps> = ({
  open,
  value,
  onChange,
}) => {
  const form = value || defaultValue;
  const typeChangeRef = useRef(true);

  useEffect(() => {
    if (open) {
      typeChangeRef.current = true;
    }
  }, [open]);

  useEffect(() => {
    if (!value) {
      onChange?.(defaultValue);
    }
  }, [value, onChange]);

  const triggerChange = (changed: Partial<EffectiveTimeValue>) => {
    onChange?.({ ...form, ...changed });
  };

  useEffect(() => {
    if (typeChangeRef.current) {
      typeChangeRef.current = false;
      return;
    }
    if (form.type === 'one') {
      triggerChange({
        start_time: dayjs().startOf('day').format('YYYY-MM-DD HH:mm:ss'),
        end_time: dayjs()
          .add(1, 'month')
          .endOf('day')
          .format('YYYY-MM-DD HH:mm:ss'),
      });
    } else {
      triggerChange({
        start_time: '00:00:00',
        end_time: '23:59:59',
      });
    }
  }, [form.type]);

  return (
    <div className="flex" id="effective-time">
      <div className="mr-[6px] flex-1">
        <Select
          value={form.type}
          onChange={(nextValue) => triggerChange({ type: nextValue })}
        >
          {timeInterval.map((item) => (
            <Option key={item.value} value={item.value}>
              {item.name}
            </Option>
          ))}
        </Select>
      </div>
      <div className="flex flex-[4]">
        {form.type === 'week' && (
          <Select
            mode="multiple"
            maxTagCount={1}
            value={form.week_month}
            onChange={(nextValue) => triggerChange({ week_month: nextValue })}
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
            onChange={(nextValue) => triggerChange({ week_month: nextValue })}
            className="flex-1"
          >
            {[...Array(31)].map((_, index) => (
              <Option key={index + 1} value={index + 1}>
                {index + 1}
              </Option>
            ))}
          </Select>
        )}
        {form.type !== 'one' && (
          <TimePicker.RangePicker
            allowClear={false}
            format="HH:mm:ss"
            className="ml-[6px] flex-1"
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
            className="ml-[6px] flex-1"
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

export default AlarmEffectiveTime;

export { defaultValue as defaultEffectiveTime };
