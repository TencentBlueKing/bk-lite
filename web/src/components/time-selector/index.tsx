import React, {
  useState,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import Icon from '@/components/icon';
import { Select, Button, DatePicker } from 'antd';
import { CalendarOutlined, ReloadOutlined } from '@ant-design/icons';
import type { SelectProps, TimeRangePickerProps } from 'antd';
import { useFrequencyList, useTimeRangeList } from '@/constants/shared';
import timeSelectorStyle from './index.module.scss';
import dayjs, { Dayjs } from 'dayjs';
import { ListItem, TimeSelectorDefaultValue } from '@/types';
type LabelRender = SelectProps['labelRender'];
const { RangePicker } = DatePicker;

interface TimeSelectorProps {
  showTime?: boolean; //rangePicker组件属性，是否显示时分秒
  format?: string; //rangePicker组件属性，格式化
  onlyRefresh?: boolean; // 仅显示刷新按钮
  onlyTimeSelect?: boolean; // 仅显示时间组合组件
  customFrequencyList?: ListItem[];
  customTimeRangeList?: ListItem[];
  clearable?: boolean; // 组件的值是否能为空
  className?: string; // 外层容器样式类名
  defaultValue?: TimeSelectorDefaultValue; // defaultValue为时间组合组件的默认值
  onFrequenceChange?: (frequence: number) => void;
  onRefresh?: () => void;
  onChange?: (range: number[], originValue: number | null) => void;
}

const TimeSelector = forwardRef((props: TimeSelectorProps, ref) => {
  const {
    showTime = true,
    format = 'YYYY-MM-DD HH:mm:ss',
    onlyRefresh = false,
    onlyTimeSelect = false,
    clearable = false,
    className,
    defaultValue = {
      selectValue: 15, // 显示select组件时，selectValue填customFrequencyList列表项中对应的value，selectValue为select组件的值。
      rangePickerVaule: null, // 如果想显示为rangePicker组件，selectValue设置为0，rangePickerVaule为rangePicker组件的值。
    },
    customFrequencyList,
    customTimeRangeList,
    onFrequenceChange,
    onRefresh,
    onChange,
  } = props;
  const TIME_RANGE_LIST = useTimeRangeList();
  const FREQUENCY_LIST = useFrequencyList();
  const rangePickerVauleRef = useRef<number[] | null>(null);
  const selectValueRef = useRef<number | null>(clearable ? null : 15);
  const [frequency, setFrequency] = useState<number>(0);
  const [rangePickerOpen, setRangePickerOpen] = useState<boolean>(false);
  const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
  const selectRef = useRef<HTMLDivElement>(null);
  const [selectValue, setSelectValue] = useState<number | null>(
    clearable ? null : 15
  );
  const [rangePickerVaule, setRangePickerVaule] = useState<
    [Dayjs, Dayjs] | null
  >(null);

  // 可以通过ref调用组件的以下方法
  useImperativeHandle(ref, () => ({
    // 获取组件当前的值
    getValue: () =>
      selectValueRef.current
        ? getRecentTimeRange()
        : rangePickerVauleRef.current,
  }));

  useEffect(() => {
    if (
      JSON.stringify(defaultValue.rangePickerVaule) !==
      JSON.stringify(rangePickerVaule)
    ) {
      setRangePickerVaule(defaultValue.rangePickerVaule);
      const _times = (defaultValue.rangePickerVaule || []).map((item) =>
        dayjs(item).valueOf()
      );
      rangePickerVauleRef.current = _times;
    }
    if (defaultValue.selectValue !== selectValue) {
      selectValueRef.current = defaultValue.selectValue;
      setSelectValue(defaultValue.selectValue);
    }
  }, [defaultValue.rangePickerVaule, defaultValue.selectValue]);

  const getRecentTimeRange = () => {
    const beginTime: number = dayjs()
      .subtract(selectValueRef.current as number, 'minute')
      .valueOf();
    const lastTime: number = dayjs().valueOf();
    return [beginTime, lastTime];
  };

  const labelRender: LabelRender = (props) => {
    const { label } = props;
    return (
      <div className="flex items-center">
        <Icon type="zidongshuaxin" className="mr-[4px] text-[16px]" />
        {label}
      </div>
    );
  };

  const handleFrequencyChange = (val: number) => {
    setFrequency(val);
    onFrequenceChange && onFrequenceChange(val);
  };

  const handleRangePickerOpenChange = (open: boolean) => {
    setRangePickerOpen(open);
  };

  const handleDropdownVisibleChange = (open: boolean) => {
    setDropdownOpen(open);
  };

  const handleIconClick = () => {
    if (selectRef.current) {
      const selectDom = selectRef.current.querySelector('.ant-select-selector');
      if (selectDom) {
        (selectDom as HTMLElement).click();
        const flag =
          !!document.querySelector('.ant-select-dropdown-hidden') ||
          !document.querySelector('.ant-select-dropdown');
        setDropdownOpen(flag);
      }
    }
  };

  const handleRangePickerChange: TimeRangePickerProps['onChange'] = (value) => {
    if (value) {
      selectValueRef.current = 0;
      setSelectValue(0);
      const rangeTime = value.map((item) => dayjs(item).valueOf());
      rangePickerVauleRef.current = rangeTime;
      onChange?.(rangeTime, 0);
      setRangePickerVaule(value as [Dayjs, Dayjs]);
      return;
    }
    const rangeTime = [
      dayjs()
        .subtract(defaultValue.selectValue || 15, 'minute')
        .valueOf(),
      dayjs().valueOf(),
    ];
    const originValue = clearable ? null : defaultValue.selectValue || 15;
    selectValueRef.current = originValue;
    setSelectValue(originValue);
    setRangePickerVaule(null);
    const latestValue = clearable ? [] : rangeTime;
    rangePickerVauleRef.current = latestValue;
    onChange?.(latestValue, originValue);
  };

  const handleRangePickerOk: TimeRangePickerProps['onOk'] = (value) => {
    if (value && value.every((item) => !!item)) {
      selectValueRef.current = 0;
      setSelectValue(0);
    }
  };

  const handleTimeRangeChange = (value: number) => {
    if (value === 0) {
      setRangePickerOpen(true);
      return;
    }
    setRangePickerVaule(null);
    selectValueRef.current = value;
    setSelectValue(value);
    const rangeTime = value
      ? [dayjs().subtract(value, 'minute').valueOf(), dayjs().valueOf()]
      : [];
    rangePickerVauleRef.current = rangeTime;
    onChange?.(rangeTime, value);
  };

  return (
    <div className={`${timeSelectorStyle.timeSelector} ${className || ''}`}>
      {!onlyRefresh && (
        <div className={timeSelectorStyle.customSlect} ref={selectRef}>
          <Select
            allowClear={clearable}
            className={`w-[350px] ${timeSelectorStyle.frequence} ${className || ''}`}
            value={selectValue}
            options={customTimeRangeList || TIME_RANGE_LIST}
            open={dropdownOpen}
            onChange={handleTimeRangeChange}
            onDropdownVisibleChange={handleDropdownVisibleChange}
          />
          <RangePicker
            style={{
              zIndex: rangePickerOpen || selectValue == 0 ? 1 : -1,
            }}
            className={`w-[350px] ${timeSelectorStyle.rangePicker} ${className || ''}`}
            open={rangePickerOpen}
            showTime={showTime}
            format={format}
            value={rangePickerVaule}
            onOpenChange={handleRangePickerOpenChange}
            onChange={handleRangePickerChange}
            onOk={handleRangePickerOk}
          />
          <CalendarOutlined
            className={timeSelectorStyle.calenIcon}
            onClick={handleIconClick}
          />
        </div>
      )}
      {!onlyTimeSelect && (
        <div className={`${timeSelectorStyle.refreshBox} flex ml-[8px]`}>
          <Button
            className={timeSelectorStyle.refreshBtn}
            icon={<ReloadOutlined />}
            onClick={onRefresh}
          />
          <Select
            className={`w-[100px] ${timeSelectorStyle.frequence}`}
            value={frequency}
            options={customFrequencyList || FREQUENCY_LIST}
            labelRender={labelRender}
            onChange={handleFrequencyChange}
          />
        </div>
      )}
    </div>
  );
});

TimeSelector.displayName = 'timeSelector';

export default TimeSelector;
