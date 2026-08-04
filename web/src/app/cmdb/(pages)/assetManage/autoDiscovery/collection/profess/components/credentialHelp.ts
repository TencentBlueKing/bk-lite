import type { ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  CREDENTIAL_DESCRIPTORS,
  getCredentialDescriptor,
  type CredentialDescriptor,
} from './credentialDescriptors';

export type CredentialHelpTranslator = (
  key: string,
  defaultMessage?: string,
) => string;

export interface CredentialFieldHelp {
  name: string;
  description: string;
  defaultValue?: string;
  recommendedValue?: string;
}

export interface CredentialHelpDefinition {
  protocol: string;
  credentialKind: string;
  instruction: string;
  defaultPort?: string;
  fields?: CredentialFieldHelp[];
}

type CredentialHelpModel = Partial<
  Pick<
    ModelItem,
    | 'model_id'
    | 'type'
    | 'credential_protocol'
    | 'credential_default_port'
  >
>;

function translateOptionalValue(
  t: CredentialHelpTranslator,
  key?: string,
  literal?: string,
) {
  if (key) {
    return t(`Collection.credentialHelp.values.${key}`);
  }
  return literal;
}

function resolveDescriptorHelp(
  descriptor: CredentialDescriptor,
  t: CredentialHelpTranslator,
  defaultPortOverride?: number,
): CredentialHelpDefinition {
  const defaultPort = defaultPortOverride ?? descriptor.defaultPort;
  return {
    protocol: t(`Collection.credentialHelp.protocol.${descriptor.protocolKey}`),
    credentialKind: t(
      `Collection.credentialHelp.kind.${descriptor.credentialKindKey}`,
    ),
    instruction: t(
      `Collection.credentialHelp.instruction.${descriptor.instructionKey}`,
    ),
    defaultPort: descriptor.defaultPortLabel
      || (defaultPort == null ? undefined : String(defaultPort)),
    fields: descriptor.fields.map((field) => ({
      name: t(`Collection.credentialHelp.fieldNames.${field.key}`),
      description: t(`Collection.credentialHelp.fields.${field.key}`),
      ...(
        field.defaultValue || field.defaultValueKey
          ? {
            defaultValue: field.key.endsWith('Port') && defaultPort != null
              ? String(defaultPort)
              : translateOptionalValue(
                t,
                field.defaultValueKey,
                field.defaultValue,
              ),
          }
          : {}
      ),
      ...(
        field.recommendedValue || field.recommendedValueKey
          ? {
            recommendedValue: translateOptionalValue(
              t,
              field.recommendedValueKey,
              field.recommendedValue,
            ),
          }
          : {}
      ),
    })),
  };
}

export function resolveCredentialHelp(
  model: CredentialHelpModel,
  t: CredentialHelpTranslator,
  override?: CredentialHelpDefinition,
): CredentialHelpDefinition {
  if (override) {
    return override;
  }
  const descriptor = getCredentialDescriptor(model);
  if (!descriptor) {
    return {
      protocol: t('Collection.credentialHelp.unavailableProtocol'),
      credentialKind: t('Collection.credentialHelp.unavailableKind'),
      instruction: t('Collection.credentialHelp.unavailableProtocol'),
    };
  }
  return resolveDescriptorHelp(
    descriptor,
    t,
    model.credential_default_port,
  );
}

export function buildSnmpCredentialHelp(
  t: CredentialHelpTranslator,
): CredentialHelpDefinition {
  return resolveDescriptorHelp(CREDENTIAL_DESCRIPTORS.protocols.snmp, t);
}

export function buildInfluxdbCredentialHelp(
  t: CredentialHelpTranslator,
): CredentialHelpDefinition {
  return resolveDescriptorHelp(CREDENTIAL_DESCRIPTORS.models.influxdb, t);
}

export function buildCloudCredentialHelp(
  modelId: string,
  t: CredentialHelpTranslator,
): CredentialHelpDefinition {
  return resolveCredentialHelp({ model_id: modelId }, t);
}

export function buildPlatformApiCredentialHelp(
  modelId: string,
  t: CredentialHelpTranslator,
): CredentialHelpDefinition {
  return resolveCredentialHelp({ model_id: modelId }, t);
}

export function buildPCCredentialHelp(
  osType: 'windows' | 'macos',
  t: CredentialHelpTranslator,
): CredentialHelpDefinition {
  return resolveDescriptorHelp(CREDENTIAL_DESCRIPTORS.pc[osType], t);
}
