import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

/**
 * Generic JSON file reader API
 * Reads JSON files from public/app directory
 * Usage: /api/json?filePath=introductions/zh/syslogVector.json
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const filePath = searchParams.get('filePath');

  if (!filePath) {
    return NextResponse.json(
      { error: 'filePath is required' },
      { status: 400 }
    );
  }

  try {
    const base = path.resolve(process.cwd(), 'public', 'app');
    const fullPath = path.resolve(base, filePath);

    if (!fullPath.startsWith(base + path.sep)) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const fileContents = fs.readFileSync(fullPath, 'utf8');
    const jsonContent = JSON.parse(fileContents);
    return NextResponse.json(jsonContent, { status: 200 });
  } catch (error) {
    console.error('Failed to read JSON file:', error);
    return NextResponse.json(
      { error: 'Failed to read the file' },
      { status: 500 }
    );
  }
}
