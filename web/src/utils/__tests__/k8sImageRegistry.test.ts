import { describe, expect, it } from 'vitest';
import {
  DEFAULT_K8S_IMAGE_REGISTRY_PREFIX,
  isValidK8sImageRegistryPrefix
} from '../k8sImageRegistry';

describe('K8s image registry prefix', () => {
  it.each([
    DEFAULT_K8S_IMAGE_REGISTRY_PREFIX,
    'harbor.internal.example/observability',
    '10.0.0.8:5000/platform/bklite',
    '[fd00::8]:5000/platform/bklite'
  ])('accepts %s', (value) => {
    expect(isValidK8sImageRegistryPrefix(value)).toBe(true);
  });

  it.each([
    '',
    'https://harbor.example/bklite',
    'harbor.example/bklite/',
    'harbor.example',
    'harbor.example/BKLite',
    'harbor.example/bklite\nimage:evil',
    'harbor.example/bklite"}}',
    'harbor.example/bklite;curl',
    'harbor.example:70000/bklite'
  ])('rejects %s', (value) => {
    expect(isValidK8sImageRegistryPrefix(value)).toBe(false);
  });
});
