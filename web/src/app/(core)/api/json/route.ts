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
    const fullPath = path.join(process.cwd(), 'public', 'app', filePath);
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
