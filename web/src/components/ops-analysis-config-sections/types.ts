export interface UnitFormatResult {
  text: string;
  value: string;
  suffix: string;
}

export interface FormatOptions {
  decimals?: number;
  conversionFactor?: number;
}

export interface UnitDef {
  id: string;
  label: string;
}

export interface UnitCategory {
  key: string;
  label: string;
  units: UnitDef[];
}

export interface ThresholdColorConfig {
  value: string;
  color: string;
}

export type ValueMappingType = 'value' | 'range' | 'regex' | 'special';

export type SpecialMatch = 'null' | 'nan' | 'empty' | 'true' | 'false';

export interface ValueMappingResult {
  text?: string;
  color?: string;
}

export interface ValueMapping {
  type: ValueMappingType;
  value?: string;
  from?: number;
  to?: number;
  pattern?: string;
  match?: SpecialMatch;
  result: ValueMappingResult;
}
