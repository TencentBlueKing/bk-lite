'use client';

import React from 'react';
import { TimePicker, Button } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';

interface TimeListFieldProps {
  value?: string[];
  onChange?: (value: string[]) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
}

const TimeListField: React.FC<TimeListFieldProps> = ({
  value = ['09:00'],
  onChange,
  min = 1,
  max,
  disabled = false,
}) => {
  const times = value.length > 0 ? value : ['09:00'];

  const handleTimeChange = (index: number, time: Dayjs | null) => {
    const newTimes = [...times];
    newTimes[index] = time ? time.format('HH:mm') : '09:00';
    onChange?.(newTimes);
  };

  const handleAdd = () => {
    if (max && times.length >= max) return;
    onChange?.([...times, '09:00']);
  };

  const handleRemove = (index: number) => {
    if (times.length <= min) return;
    const newTimes = times.filter((_, i) => i !== index);
    onChange?.(newTimes);
  };

  const parseTime = (timeStr: string): Dayjs => {
    const [hour, minute] = timeStr.split(':').map(Number);
    return dayjs().hour(hour).minute(minute);
  };

  return (
    <div className="flex flex-col gap-2">
      {times.map((time, index) => (
        <div key={index} className="flex items-center gap-2">
          <TimePicker
            value={parseTime(time)}
            format="HH:mm"
            onChange={(t) => handleTimeChange(index, t)}
            className="flex-1"
            disabled={disabled}
            allowClear={false}
          />
          {index === times.length - 1 ? (
            <Button
              type="text"
              icon={<PlusOutlined />}
              onClick={handleAdd}
              disabled={disabled || (max !== undefined && times.length >= max)}
              className="text-[#00b42a] hover:text-[#00b42a]/80"
            />
          ) : (
            <Button
              type="text"
              icon={<DeleteOutlined />}
              onClick={() => handleRemove(index)}
              disabled={disabled || times.length <= min}
              className="text-gray-400 hover:text-gray-600"
            />
          )}
        </div>
      ))}
    </div>
  );
};

export default TimeListField;
