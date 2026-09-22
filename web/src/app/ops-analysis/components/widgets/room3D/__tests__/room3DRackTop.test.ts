import { describe, expect, it } from 'vitest';
import { resolveRoom3DRackTopTextureLines } from '../room3DRackTop';
import { validateRoom3DData, type Room3DRack } from '../room3DData';

const identity = (id: string) => id;

const rack: Room3DRack = {
  rack_id: 'rack-1',
  rack_name: '机柜ABCDEFGH',
  row: 1,
  col: 1,
  location: 'A01',
  rack_type_name: '网络柜',
  rack_state_name: '启用',
};

describe('resolveRoom3DRackTopTextureLines', () => {
  it('defaults to location then type at the existing widths', () => {
    expect(resolveRoom3DRackTopTextureLines(rack)).toEqual({
      line1: 'A01',
      line2: '网络柜',
    });
  });

  it('truncates rack names at the current first-line and second-line widths', () => {
    expect(
      resolveRoom3DRackTopTextureLines(rack, {
        line1: 'name',
        line2: 'state',
      }),
    ).toEqual({
      line1: '机柜ABC',
      line2: '启用',
    });
    expect(
      resolveRoom3DRackTopTextureLines(rack, {
        line1: 'location',
        line2: 'name',
      }),
    ).toEqual({
      line1: 'A01',
      line2: '机柜ABCDEF',
    });
  });

  it('allows duplicate fields and hides an empty second line', () => {
    expect(
      resolveRoom3DRackTopTextureLines(rack, {
        line1: 'location',
        line2: 'location',
      }),
    ).toEqual({
      line1: 'A01',
      line2: 'A01',
    });
    expect(
      resolveRoom3DRackTopTextureLines(rack, {
        line1: 'name',
        line2: '',
      }),
    ).toEqual({
      line1: '机柜ABC',
    });
  });

  it('uses rack_state when the readable name is missing but the stored value is already a label', () => {
    expect(
      resolveRoom3DRackTopTextureLines(
        { ...rack, rack_state_name: undefined, rack_state: '启用' },
        { line1: 'location', line2: 'state' },
      ),
    ).toEqual({
      line1: 'A01',
      line2: '启用',
    });
  });
});

describe('validateRoom3DData rack state', () => {
  it('keeps rack_state_name for the top label', () => {
    const result = validateRoom3DData(
      {
        room: { id: 'room-1', name: 'Room A' },
        racks: [
          {
            rack_id: 'rack-1',
            rack_name: 'R1',
            row: 1,
            col: 1,
            rack_state: '1',
            rack_state_name: '启用',
          },
        ],
      },
      identity,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.racks[0].rack_state).toBe('1');
    expect(result.data.racks[0].rack_state_name).toBe('启用');
  });

  it('keeps a list or numeric rack_state for the top label', () => {
    const listed = validateRoom3DData(
      {
        room: { id: 'room-1', name: 'Room A' },
        racks: [
          {
            rack_id: 'rack-1',
            rack_name: 'R1',
            row: 1,
            col: 1,
            rack_state: ['1'],
          },
        ],
      },
      identity,
    );
    expect(listed.ok).toBe(true);
    if (!listed.ok) return;
    expect(listed.data.racks[0].rack_state).toBe('1');
  });
});
