const expectedFiles = [
  'LICENSE',
  'NOTICE',
  'README.md',
  'dist/batches.d.ts',
  'dist/index.d.ts',
  'dist/index.js',
  'dist/index.js.map',
  'dist/queue.d.ts',
  'dist/replay-privacy.d.ts',
  'dist/replay.d.ts',
  'dist/retry.d.ts',
  'dist/transport.d.ts',
  'package.json',
  'sbom.cdx.json',
];

const result = Bun.spawnSync({
  cmd: [process.execPath, 'pm', 'pack', '--dry-run', '--ignore-scripts'],
  stderr: 'pipe',
  stdout: 'pipe',
});
const output = `${result.stdout.toString()}\n${result.stderr.toString()}`;
if (result.exitCode !== 0) {
  process.stderr.write(output);
  throw new Error('bun pm pack --dry-run failed');
}

const packedFiles = output
  .split('\n')
  .map((line) => line.match(/^packed\s+\S+\s+(.+)$/)?.[1])
  .filter((value): value is string => Boolean(value))
  .sort();

if (JSON.stringify(packedFiles) !== JSON.stringify(expectedFiles)) {
  throw new Error(
    `unexpected package contents\nexpected: ${expectedFiles.join(', ')}\nactual: ${packedFiles.join(', ')}`,
  );
}

console.log(`package contents verified (${packedFiles.length} files)`);
