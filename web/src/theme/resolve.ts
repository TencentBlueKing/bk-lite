import { defaultTheme } from './defaults';
import type { ResolvedTheme, ThemeDefinition } from './contract';

const resolveMode = (
  defaults: ResolvedTheme['light'],
  overrides: ThemeDefinition['light']
) => ({
  ...defaults,
  ...overrides,
  chartPrimary: overrides.chartPrimary
    ?? overrides.interactionPrimary
    ?? defaults.chartPrimary,
});

export const resolveTheme = (definition: ThemeDefinition): ResolvedTheme => ({
  themeId: definition.themeId,
  themeVersion: definition.themeVersion,
  schemaVersion: definition.schemaVersion,
  light: resolveMode(defaultTheme.light, definition.light),
  dark: resolveMode(defaultTheme.dark, definition.dark),
});
