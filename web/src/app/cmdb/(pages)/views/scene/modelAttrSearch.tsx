'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Checkbox,
  DatePicker,
  Input,
  InputNumber,
  Select,
} from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import type { AttrFieldType, UserItem } from '@/app/cmdb/types/assetManage';
import { getEnumOptions, getTagOptions } from '@/app/cmdb/utils/fieldUtils';
import {
  buildAttrSearchCondition,
  defaultSearchField,
  searchableAttrs,
} from './attrSearchCondition';
import type { ModelSearchPreference } from './tagViewSearchPreference';

dayjs.extend(customParseFormat);

const ATTR_SELECT_WIDTH = 120;
const VALUE_CONTROL_WIDTH = 200;

interface ModelAttrSearchProps {
  attrList: AttrFieldType[];
  userList: UserItem[];
  proxyOptions: Array<{ proxy_id: string; proxy_name: string }>;
  preference?: ModelSearchPreference;
  onCommit: (preference: ModelSearchPreference) => void;
}

const joinedControlClass =
  '[&_.ant-select-selector]:rounded-none [&_.ant-input]:rounded-none [&_.ant-input-number]:rounded-none [&_.ant-picker]:rounded-none';

const ModelAttrSearch: React.FC<ModelAttrSearchProps> = ({
  attrList,
  userList,
  proxyOptions,
  preference,
  onCommit,
}) => {
  const { t } = useTranslation();
  const { RangePicker } = DatePicker;
  const attrs = useMemo(() => searchableAttrs(attrList), [attrList]);
  const fallbackField = defaultSearchField(attrs);
  const [field, setField] = useState(preference?.field || fallbackField);
  const [value, setValue] = useState<unknown>(preference?.value);
  const [exact, setExact] = useState(Boolean(preference?.exact));

  useEffect(() => {
    setField(preference?.field || '');
    setValue(preference?.value);
    setExact(Boolean(preference?.exact));
  }, [preference?.field, preference?.value, preference?.exact]);

  useEffect(() => {
    setField((current) => current || fallbackField);
  }, [fallbackField]);

  const selectedAttr = attrs.find((attr) => attr.attr_id === field);

  const commit = (nextField: string, nextValue: unknown, nextExact: boolean) => {
    const attr = attrs.find((item) => item.attr_id === nextField);
    onCommit({
      field: nextField,
      value: nextValue,
      exact: nextExact,
      clause: buildAttrSearchCondition(attr, nextValue, nextExact),
    });
  };

  const handleFieldChange = (nextField: string) => {
    setField(nextField);
    setValue(undefined);
    onCommit({ field: nextField, value: undefined, exact, clause: null });
  };

  const handleValueCommit = (nextValue: unknown) => {
    setValue(nextValue);
    commit(field, nextValue, exact);
  };

  const renderValueInput = () => {
    if (selectedAttr?.attr_id === 'cloud' && proxyOptions.length) {
      return (
        <Select
          size="small"
          allowClear
          showSearch
          placeholder={t('common.selectTip')}
          className={joinedControlClass}
          style={{ width: VALUE_CONTROL_WIDTH }}
          value={value as string | number | undefined}
          onChange={(next) => handleValueCommit(next)}
          onClear={() => handleValueCommit('')}
        >
          {proxyOptions.map((opt) => (
            <Select.Option key={opt.proxy_id} value={opt.proxy_id}>
              {opt.proxy_name}
            </Select.Option>
          ))}
        </Select>
      );
    }

    switch (selectedAttr?.attr_type) {
      case 'user':
        return (
          <Select
            size="small"
            mode="multiple"
            allowClear
            showSearch
            className={joinedControlClass}
            style={{ minWidth: VALUE_CONTROL_WIDTH }}
            value={Array.isArray(value) ? value : value ? [value] : []}
            onChange={(next) => handleValueCommit(next)}
            onClear={() => handleValueCommit([])}
            maxTagCount={2}
            maxTagPlaceholder={(omitted) => `+${omitted.length}`}
            filterOption={(input, opt: { children?: { props?: { text?: string } } }) => {
              const text = opt?.children?.props?.text;
              return typeof text === 'string'
                ? text.toLowerCase().includes(input.toLowerCase())
                : true;
            }}
          >
            {userList.map((opt) => (
              <Select.Option key={opt.id} value={opt.id}>
                <EllipsisWithTooltip
                  text={`${String(opt.display_name || opt.username)}(${opt.username})`}
                  className="overflow-hidden text-ellipsis whitespace-nowrap break-all"
                />
              </Select.Option>
            ))}
          </Select>
        );
      case 'enum': {
        const enumOpts = getEnumOptions(selectedAttr);
        const multiple = selectedAttr.enum_select_mode === 'multiple';
        return (
          <Select
            size="small"
            mode={multiple ? 'multiple' : undefined}
            allowClear
            showSearch
            className={joinedControlClass}
            style={{ width: multiple ? undefined : VALUE_CONTROL_WIDTH, minWidth: VALUE_CONTROL_WIDTH }}
            value={
              multiple
                ? Array.isArray(value)
                  ? value
                  : value
                    ? [value]
                    : []
                : value
            }
            onChange={(next) => handleValueCommit(next)}
            onClear={() => handleValueCommit(multiple ? [] : '')}
            maxTagCount={2}
            filterOption={(input, opt) =>
              typeof opt?.label === 'string'
                ? opt.label.toLowerCase().includes(input.toLowerCase())
                : true
            }
            options={enumOpts}
          />
        );
      }
      case 'tag':
        return (
          <Select
            size="small"
            mode="multiple"
            allowClear
            showSearch
            className={joinedControlClass}
            style={{ minWidth: 220 }}
            value={Array.isArray(value) ? value : value ? [value] : []}
            onChange={(next) => handleValueCommit(next)}
            onClear={() => handleValueCommit([])}
            maxTagCount={2}
            options={getTagOptions(selectedAttr)}
          />
        );
      case 'bool':
        return (
          <Select
            size="small"
            allowClear
            className={joinedControlClass}
            style={{ width: VALUE_CONTROL_WIDTH }}
            value={value as boolean | undefined}
            onChange={(next) => handleValueCommit(next)}
            onClear={() => handleValueCommit('')}
          >
            <Select.Option value={true}>Yes</Select.Option>
            <Select.Option value={false}>No</Select.Option>
          </Select>
        );
      case 'organization':
        return (
          <GroupTreeSelector
            style={{ width: VALUE_CONTROL_WIDTH }}
            value={(Array.isArray(value) ? value : []) as number[]}
            onChange={(next) => handleValueCommit(next)}
          />
        );
      case 'time': {
        const startRaw = Array.isArray(value) ? value[0] : null;
        const endRaw = Array.isArray(value) ? value[1] : null;
        const toDayjs = (item: unknown) => {
          if (!item) return null;
          if (typeof item === 'object' && item !== null && 'isValid' in item) {
            return item as dayjs.Dayjs;
          }
          const parsed = dayjs(String(item), 'YYYY-MM-DD HH:mm', true);
          return parsed.isValid() ? parsed : dayjs(String(item));
        };
        return (
          <RangePicker
            size="small"
            allowClear
            className={joinedControlClass}
            style={{ width: 280 }}
            showTime={{ format: 'HH:mm' }}
            format="YYYY-MM-DD HH:mm"
            value={[toDayjs(startRaw), toDayjs(endRaw)] as [dayjs.Dayjs | null, dayjs.Dayjs | null]}
            onChange={(_range, dateString) => handleValueCommit(dateString)}
          />
        );
      }
      case 'int':
        return (
          <InputNumber
            size="small"
            className={joinedControlClass}
            style={{ width: VALUE_CONTROL_WIDTH }}
            value={typeof value === 'number' ? value : undefined}
            onChange={(next) => setValue(next)}
            onPressEnter={() => handleValueCommit(value)}
          />
        );
      default:
        return (
          <Input
            size="small"
            allowClear
            className={joinedControlClass}
            style={{ width: VALUE_CONTROL_WIDTH }}
            value={typeof value === 'string' ? value : value == null ? '' : String(value)}
            placeholder={t('SceneView.searchPlaceholder')}
            onChange={(event) => setValue(event.target.value)}
            onPressEnter={() => handleValueCommit(value)}
            onClear={() => handleValueCommit('')}
          />
        );
    }
  };

  return (
    <div className="flex items-center">
      <Select
        size="small"
        value={field || undefined}
        onChange={handleFieldChange}
        style={{ width: ATTR_SELECT_WIDTH }}
        className="[&_.ant-select-selector]:rounded-r-none"
        options={attrs.map((attr) => ({
          value: attr.attr_id,
          label: attr.attr_name,
        }))}
      />
      {renderValueInput()}
      <Button
        size="small"
        type="primary"
        icon={<SearchOutlined />}
        className="rounded-l-none"
        aria-label={t('SceneView.searchPlaceholder')}
        onClick={() => handleValueCommit(value)}
      />
      {selectedAttr?.attr_type === 'str' && (
        <Checkbox
          className="ml-2"
          checked={exact}
          onChange={(event) => {
            const nextExact = event.target.checked;
            setExact(nextExact);
            commit(field, value, nextExact);
          }}
        >
          {t('Model.isExactSearch_abbreviation')}
        </Checkbox>
      )}
    </div>
  );
};

export default ModelAttrSearch;
