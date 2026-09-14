import { describe, expect, it } from 'vitest';

import { canShowCrossModulePublicWidget } from '../crossModuleEmbed';

describe('canShowCrossModulePublicWidget', () => {
  it('hides a cross-module widget when ops-analysis is not sold', () => {
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: false,
        providerDeclared: true,
      }),
    ).toBe(false);
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'cmdb.baseInfo',
        hasOpsAnalysis: false,
        providerDeclared: true,
      }),
    ).toBe(false);
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'cmdb',
        widgetKey: 'monitor.alertList',
        hasOpsAnalysis: false,
        providerDeclared: true,
      }),
    ).toBe(false);
  });

  it('shows a cross-module widget when ops-analysis is sold and the provider declared it', () => {
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: true,
        providerDeclared: true,
      }),
    ).toBe(true);
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'cmdb',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: true,
        providerDeclared: true,
      }),
    ).toBe(true);
  });

  it('keeps same-module embeds off the extra ops-analysis gate', () => {
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'monitor',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: false,
        providerDeclared: true,
      }),
    ).toBe(true);
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'ops-analysis',
        widgetKey: 'ops-analysis.relatedTopology',
        hasOpsAnalysis: false,
        providerDeclared: true,
      }),
    ).toBe(true);
  });

  it('stays hidden when the providing module did not declare the widget', () => {
    expect(
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: true,
        providerDeclared: false,
      }),
    ).toBe(false);
  });
});
