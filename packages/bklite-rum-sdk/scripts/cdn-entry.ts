// CDN entry: self-contained IIFE for the generated <script src> snippet.
// Bundles @grafana/faro-web-sdk so a no-build site can call window.initCoreRum.
import { initCoreRum } from '../src/cdn.ts';

const root = globalThis as typeof globalThis & { initCoreRum: typeof initCoreRum };
root.initCoreRum = initCoreRum;
