import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import MatchRule from '../../(pages)/settings/components/matchRule';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {} }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => ({
  getAlertSourceOptions: async () => [],
  getPushSourceIdOptions: async () => [],
}) }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }); });

describe('监控源类型和 AND/OR 结构', () => {
  it.each(['push_source_ids', 'push_source_id'] as const)('%s 条件和条件组按钮保持结构', async field => {
    const onChange = vi.fn();
    const condition = { key: field, operator: field === 'push_source_ids' ? 'all_of' : 'any_of', value: ['001','1'] };
    render(<MatchRule monitorSourceField={field} value={[[condition]]} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'alarmCommon.addRuleCondition' }));
    expect(onChange).toHaveBeenLastCalledWith([[condition, { key: undefined, operator: undefined, value: undefined }]]);
    fireEvent.click(screen.getAllByRole('button', { name: 'alarmCommon.removeRuleCondition' })[1]);
    expect(onChange).toHaveBeenLastCalledWith([[condition]]);
    fireEvent.click(screen.getByRole('button', { name: 'alarmCommon.addRuleGroup' }));
    expect(onChange).toHaveBeenLastCalledWith([[condition], [{key:undefined,operator:undefined,value:undefined}]]);
    fireEvent.click(screen.getAllByRole('button', { name: 'alarmCommon.removeRuleGroup' })[1]);
    expect(onChange).toHaveBeenLastCalledWith([[condition]]);
  });
  it('屏蔽监控源为 any_of 数组，保留前导零', () => {
    const onChange=vi.fn();
    render(<MatchRule scope="shield" value={[[{key:'push_source_id',operator:'any_of',value:['001']}]]} onChange={onChange} />);
    const input=screen.getByRole('combobox',{name:'alarmCommon.pushSourceInput'});
    fireEvent.change(input,{target:{value:'0001'}});
    fireEvent.keyDown(input,{key:'Enter',keyCode:13});
    expect(onChange).toHaveBeenLastCalledWith([[{key:'push_source_id',operator:'any_of',value:['001','0001']}]]);
  });
});
