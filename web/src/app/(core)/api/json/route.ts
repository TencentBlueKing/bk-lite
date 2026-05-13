import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const JSON_BASE_DIRECTORIES = [
  path.resolve(process.cwd(), 'public', 'app'),
  path.resolve(process.cwd(), 'src', 'app', 'log', 'public'),
];

const resolveJsonFilePath = (relativePath: string) => {
  for (const base of JSON_BASE_DIRECTORIES) {
    const fullPath = path.resolve(base, relativePath);
    if (!fullPath.startsWith(base + path.sep)) {
      continue;
    }
    if (fs.existsSync(fullPath)) {
      return fullPath;
    }
  }

  return null;
};

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
    const fullPath = resolveJsonFilePath(filePath);
    if (!fullPath) {
      return NextResponse.json({ error: 'File not found' }, { status: 404 });
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
