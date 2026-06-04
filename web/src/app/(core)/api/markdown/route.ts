import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { resolveVersionMarkdownPath } from '../version-log-path';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const filePath = searchParams.get('filePath');

  if (!filePath) {
    return NextResponse.json({ error: 'filePath is required' }, { status: 400 });
  }

  try {
    let fullPath: string;

    if (filePath.startsWith('versions/')) {
      const resolvedVersionPath = resolveVersionMarkdownPath(filePath);
      if (!resolvedVersionPath) {
        return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
      }
      if (!resolvedVersionPath.exists) {
        return NextResponse.json({ error: 'File not found' }, { status: 404 });
      }
      fullPath = resolvedVersionPath.fullPath;
    } else {
      const base = path.resolve(process.cwd(), 'public', 'app');
      fullPath = path.resolve(base, filePath);

      if (!fullPath.startsWith(base + path.sep)) {
        return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
      }
    }

    const fileContents = fs.readFileSync(fullPath, 'utf8');
    return NextResponse.json({ content: fileContents }, { status: 200 });
  } catch {
    return NextResponse.json({ error: 'Failed to read the file' }, { status: 500 });
  }
}
