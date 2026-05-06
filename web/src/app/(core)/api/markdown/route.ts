import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const filePath = searchParams.get('filePath');

  if (!filePath) {
    return NextResponse.json({ error: 'filePath is required' }, { status: 400 });
  }

  try {
    const base = path.resolve(process.cwd(), 'public', 'app');
    const fullPath = path.resolve(base, filePath);

    if (!fullPath.startsWith(base + path.sep)) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const fileContents = fs.readFileSync(fullPath, 'utf8');
    return NextResponse.json({ content: fileContents }, { status: 200 });
  } catch {
    return NextResponse.json({ error: 'Failed to read the file' }, { status: 500 });
  }
}
