import fs from 'node:fs';
import path from 'node:path';

const webRoot = process.cwd();
const devTypes = path.join(webRoot, '.next', 'dev', 'types');
const buildTypes = path.join(webRoot, '.next', 'types');
const envPath = path.join(webRoot, 'next-env.d.ts');

if (fs.existsSync(devTypes)) {
  fs.mkdirSync(buildTypes, { recursive: true });
  fs.cpSync(devTypes, buildTypes, { recursive: true });
}

if (fs.existsSync(envPath)) {
  const next = fs.readFileSync(envPath, 'utf8').replaceAll('.next/dev/types', '.next/types');
  fs.writeFileSync(envPath, next);
}
