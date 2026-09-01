import type {
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '@/app/cmdb/types/applicationResourceOverview';
import { type LayerKey } from './layerLayout';

export const MODEL_APP_TOPO_LAYERS = [
  'system',
  'service',
  'host',
  'appService',
  'infrastructure',
  'none',
] as const;

export type ModelAppTopoLayer = (typeof MODEL_APP_TOPO_LAYERS)[number];

const MODEL_LAYER_SET = new Set<string>(MODEL_APP_TOPO_LAYERS);
const BAND_LAYER_SET = new Set<string>(['service', 'host', 'appService', 'infrastructure']);
const HOST_LAYER_MODEL_RE = /(_vm|_ecs|_cvm|_ec2)$/;

export function isModelAppTopoLayer(value: unknown): value is ModelAppTopoLayer {
  return typeof value === 'string' && MODEL_LAYER_SET.has(value);
}

export function resolveLayer(
  topology: ApplicationResourceTopologyData,
  node: ApplicationResourceNode,
  rootNode: ApplicationResourceNode
): LayerKey | null {
  if (node.id === rootNode.id) return 'root';
  if (node.app_topo_layer === 'none') return null;
  if (node.app_topo_layer === 'system' || node.model_id === 'system') return 'root';
  if (typeof node.app_topo_layer === 'string' && BAND_LAYER_SET.has(node.app_topo_layer)) {
    return node.app_topo_layer as LayerKey;
  }
  if (node.category === 'application' || node.model_id === 'application') return 'service';
  if (
    node.model_id === 'host' ||
    node.model_id === 'manageone_server' ||
    HOST_LAYER_MODEL_RE.test(node.model_id || '')
  ) {
    return 'host';
  }
  if (
    node.category === 'middleware' ||
    node.category === 'database' ||
    node.category === 'cache' ||
    node.category === 'message_queue'
  ) {
    return 'appService';
  }
  if (node.category === 'hardware' || node.category === 'rack_room') {
    return 'infrastructure';
  }
  return null;
}
