import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  availableConfigSections,
  pickConfigErrorSection,
  planValidationFailure,
  sectionErrorFlagsFromNames,
  sectionForConfigField,
} from '../configSectionErrors';

describe('sectionForConfigField', () => {
  it('maps interaction and single style by the first name segment', () => {
    assert.equal(sectionForConfigField(['interaction', 'url']), 'interaction');
    assert.equal(sectionForConfigField(['singleStyle']), 'singleStyle');
    assert.equal(sectionForConfigField('interaction'), 'interaction');
    assert.equal(sectionForConfigField('name'), 'visible');
  });

  it('keeps always-visible fields off the tabs', () => {
    for (const name of ['name', 'description', 'dataSource', 'chartType']) {
      assert.equal(sectionForConfigField([name]), 'visible');
    }
  });

  it('defaults data-section and unknown fields to data', () => {
    assert.equal(sectionForConfigField(['params', 'query']), 'data');
    assert.equal(sectionForConfigField(['cardList', 'titleField']), 'data');
    assert.equal(sectionForConfigField(['radar', 'indicators', 0, 'key']), 'data');
    assert.equal(sectionForConfigField(['eventTimeline', 'timeField']), 'data');
    assert.equal(sectionForConfigField(['networkStatusTopology', 'instUuids']), 'data');
    assert.equal(sectionForConfigField(['relatedTopology', 'modelId']), 'data');
    assert.equal(sectionForConfigField(['room3D', 'rackTopLine1']), 'data');
    assert.equal(sectionForConfigField(['selectedFields']), 'data');
    assert.equal(sectionForConfigField(['gaugeMin']), 'data');
    assert.equal(sectionForConfigField(['multiValueLabelField']), 'data');
    assert.equal(sectionForConfigField(['topNLabelField']), 'data');
    assert.equal(sectionForConfigField(['nodeGraphSourceField']), 'data');
    assert.equal(sectionForConfigField(['chartThemeMode']), 'data');
    assert.equal(sectionForConfigField(['notARealField']), 'data');
    assert.equal(sectionForConfigField([0, 'key']), 'data');
  });

  it('cannot map a field without a name', () => {
    assert.equal(sectionForConfigField(undefined), null);
    assert.equal(sectionForConfigField([]), null);
  });
});

describe('pickConfigErrorSection', () => {
  it('stays when the current section already has an error', () => {
    assert.equal(
      pickConfigErrorSection({
        current: 'interaction',
        errored: ['data', 'interaction'],
      }),
      'interaction',
    );
    assert.equal(
      pickConfigErrorSection({
        current: 'data',
        errored: ['interaction', 'data'],
      }),
      'data',
    );
  });

  it('prefers data, then style, then interaction when leaving the current section', () => {
    assert.equal(
      pickConfigErrorSection({
        current: 'singleStyle',
        errored: ['interaction', 'data'],
      }),
      'data',
    );
    assert.equal(
      pickConfigErrorSection({
        current: 'data',
        errored: ['interaction', 'singleStyle'],
      }),
      'singleStyle',
    );
    assert.equal(
      pickConfigErrorSection({
        current: 'interaction',
        errored: ['data'],
      }),
      'data',
    );
  });

  it('ignores sections that are not on this surface', () => {
    assert.equal(
      pickConfigErrorSection({
        current: 'interaction',
        errored: ['singleStyle'],
        available: availableConfigSections({ variant: 'panel', showSingleStyle: false }),
      }),
      null,
    );
  });
});

describe('planValidationFailure', () => {
  const available = availableConfigSections({
    variant: 'drawer',
    showSingleStyle: true,
  });

  it('falls back when nothing can be mapped', () => {
    assert.equal(
      planValidationFailure({ error: new Error('nope'), current: 'data', available }).fallback,
      true,
    );
    assert.equal(
      planValidationFailure({
        error: { errorFields: [{ name: [] }] },
        current: 'interaction',
        available,
      }).fallback,
      true,
    );
  });

  it('does not switch tabs for an always-visible field', () => {
    const plan = planValidationFailure({
      error: { errorFields: [{ name: ['name'] }] },
      current: 'interaction',
      available,
    });
    assert.equal(plan.fallback, false);
    assert.equal(plan.section, null);
    assert.deepEqual(plan.namePath, ['name']);
    assert.deepEqual(plan.errors, {
      data: false,
      singleStyle: false,
      interaction: false,
    });
  });

  it('scrolls to the first error in the chosen section', () => {
    const plan = planValidationFailure({
      error: {
        errorFields: [
          { name: ['name'] },
          { name: ['cardList', 'titleField'] },
          { name: ['interaction', 'url'] },
          { name: ['selectedFields'] },
        ],
      },
      current: 'singleStyle',
      available,
    });
    assert.equal(plan.section, 'data');
    assert.deepEqual(plan.namePath, ['cardList', 'titleField']);
    assert.equal(plan.errors.data, true);
    assert.equal(plan.errors.interaction, true);
    assert.equal(plan.errors.singleStyle, false);
  });

  it('keeps the interaction error when that tab is already showing it', () => {
    const plan = planValidationFailure({
      error: {
        errorFields: [
          { name: ['selectedFields'] },
          { name: ['interaction', 'name'] },
          { name: ['interaction', 'url'] },
        ],
      },
      current: 'interaction',
      available,
    });
    assert.equal(plan.section, 'interaction');
    assert.deepEqual(plan.namePath, ['interaction', 'name']);
  });
});

describe('sectionErrorFlagsFromNames', () => {
  it('ignores fields that currently have no errors', () => {
    assert.deepEqual(
      sectionErrorFlagsFromNames([
        { name: ['interaction', 'url'], errors: [] },
        { name: ['selectedFields'], errors: ['required'] },
      ]),
      { data: true, singleStyle: false, interaction: false },
    );
  });
});
