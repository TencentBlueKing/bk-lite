import React, {
  useState,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import Icon from '@/components/icon';
import { Select, Button, DatePicker } from 'antd';
import { CalendarOutlined, CloseCircleFilled, ReloadOutlined } from '@ant-design/icons';
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
  const openCustomTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressPickerCloseRef = useRef(false);
  const confirmingCustomRangeRef = useRef(false);
  // 进入自定义前的预设分钟数，取消时还原。
  const lastPresetValueRef = useRef<number>(
    defaultValue.selectValue && defaultValue.selectValue !== 0
      ? defaultValue.selectValue
      : 15
  );
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
  // 面板打开中，或已确认自定义区间：只展示 RangePicker，避免与 Select 叠出双层边框。
  const pickerVisible = rangePickerOpen || selectValue === 0;

  // 可以通过ref调用组件的以下方法
  useImperativeHandle(ref, () => ({
    // 获取组件当前的值
    getValue: () =>
      selectValueRef.current
        ? getRecentTimeRange()
        : rangePickerVauleRef.current,
  }));

  useEffect(() => {
    return () => {
      if (openCustomTimerRef.current) {
        clearTimeout(openCustomTimerRef.current);
      }
    };
  }, []);

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
    const lastTime = dayjs();
    const beginTime: number = lastTime
      .subtract(selectValueRef.current as number, 'minute')
      .valueOf();
    return [beginTime, lastTime.valueOf()];
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
    // Select 选「自定义」关闭时的 outside-click 会误关刚打开的 RangePicker，短暂忽略 close。
    if (!open && suppressPickerCloseRef.current) {
      return;
    }
    setRangePickerOpen(open);
  };

  const handleDropdownVisibleChange = (open: boolean) => {
    setDropdownOpen(open);
  };

  const openCustomRangePicker = () => {
    if (selectValueRef.current && selectValueRef.current !== 0) {
      lastPresetValueRef.current = selectValueRef.current;
    }
    setDropdownOpen(false);
    suppressPickerCloseRef.current = true;
    if (openCustomTimerRef.current) {
      clearTimeout(openCustomTimerRef.current);
    }
    openCustomTimerRef.current = setTimeout(() => {
      setRangePickerOpen(true);
      openCustomTimerRef.current = setTimeout(() => {
        suppressPickerCloseRef.current = false;
        openCustomTimerRef.current = null;
      }, 200);
    }, 50);
  };

  const handleCancelCustom = () => {
    const preset =
      lastPresetValueRef.current || defaultValue.selectValue || 15;
    confirmingCustomRangeRef.current = false;
    suppressPickerCloseRef.current = false;
    if (openCustomTimerRef.current) {
      clearTimeout(openCustomTimerRef.current);
      openCustomTimerRef.current = null;
    }
    setRangePickerOpen(false);
    setRangePickerVaule(null);
    selectValueRef.current = preset;
    setSelectValue(preset);
    const rangeTime = [
      dayjs().subtract(preset, 'minute').valueOf(),
      dayjs().valueOf(),
    ];
    rangePickerVauleRef.current = rangeTime;
    onChange?.(rangeTime, preset);
  };

  const handleIconClick = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (pickerVisible) {
      handleCancelCustom();
      return;
    }
    // 日历图标：直接进入自定义时间，不再打开预设 Select。
    openCustomRangePicker();
  };

  const handleRangePickerChange: TimeRangePickerProps['onChange'] = (value) => {
    if (value) {
      confirmingCustomRangeRef.current = true;
      selectValueRef.current = 0;
      setSelectValue(0);
      const rangeTime = value.map((item) => dayjs(item).valueOf());
      rangePickerVauleRef.current = rangeTime;
      onChange?.(rangeTime, 0);
      setRangePickerVaule(value as [Dayjs, Dayjs]);
      setRangePickerOpen(false);
      return;
    }
    // showTime + 受控 open 在确认关闭时可能再抛一次 null，忽略以免清掉刚确认的自定义区间。
    if (confirmingCustomRangeRef.current) {
      confirmingCustomRangeRef.current = false;
      return;
    }
    if (selectValueRef.current === 0 && rangePickerVauleRef.current?.length) {
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
      suppressPickerCloseRef.current = false;
      confirmingCustomRangeRef.current = true;
      selectValueRef.current = 0;
      setSelectValue(0);
      const rangeTime = value.map((item) => dayjs(item).valueOf());
      rangePickerVauleRef.current = rangeTime;
      setRangePickerVaule(value as [Dayjs, Dayjs]);
      onChange?.(rangeTime, 0);
      setRangePickerOpen(false);
    }
  };

  const handleTimeRangeChange = (value: number | string) => {
    const numericValue = Number(value);
    if (numericValue === 0) {
      // 保持原有叠层：不先把 selectValue 置 0（否则会空出「开始/结束日期」且打乱交互）。
      openCustomRangePicker();
      return;
    }
    if (openCustomTimerRef.current) {
      clearTimeout(openCustomTimerRef.current);
      openCustomTimerRef.current = null;
    }
    suppressPickerCloseRef.current = false;
    setRangePickerOpen(false);
    setRangePickerVaule(null);
    lastPresetValueRef.current = numericValue;
    selectValueRef.current = numericValue;
    setSelectValue(numericValue);
    const rangeTime = numericValue
      ? [dayjs().subtract(numericValue, 'minute').valueOf(), dayjs().valueOf()]
      : [];
    rangePickerVauleRef.current = rangeTime;
    onChange?.(rangeTime, numericValue);
  };

  return (
    <div
      className={`${timeSelectorStyle.timeSelector} ${
        selectValue === 0 ? timeSelectorStyle.customActive : ''
      } ${pickerVisible ? timeSelectorStyle.pickerVisible : ''} ${className || ''}`}
    >
      {!onlyRefresh && (
        <div className={timeSelectorStyle.customSlect} ref={selectRef}>
          <Select
            allowClear={clearable}
            className={`w-[350px] ${timeSelectorStyle.frequence} ${className || ''}`}
            value={selectValue}
            options={customTimeRangeList || TIME_RANGE_LIST}
            open={dropdownOpen}
            onChange={handleTimeRangeChange}
            onOpenChange={handleDropdownVisibleChange}
          />
          <RangePicker
            className={`w-[350px] ${timeSelectorStyle.rangePicker} ${className || ''}`}
            popupClassName={timeSelectorStyle.rangePickerDropdown}
            open={rangePickerOpen}
            showTime={showTime}
            format={format}
            value={rangePickerVaule}
            placement="bottomLeft"
            onOpenChange={handleRangePickerOpenChange}
            onChange={handleRangePickerChange}
            onOk={handleRangePickerOk}
            allowClear={false}
            inputReadOnly
            getPopupContainer={() => document.body}
          />
          {pickerVisible ? (
            <CloseCircleFilled
              className={`${timeSelectorStyle.calenIcon} ${timeSelectorStyle.clearCustomIcon}`}
              onClick={handleIconClick}
            />
          ) : (
            <CalendarOutlined
              className={timeSelectorStyle.calenIcon}
              onClick={handleIconClick}
            />
          )}
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
