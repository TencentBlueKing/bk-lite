import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const GET = async (request: NextRequest) => {
  try {
    const { searchParams } = new URL(request.url);
    const locale = searchParams.get('locale') === 'en' ? 'en' : 'zh';

    const versionsDirectory = path.join(process.cwd(), `public/app/versions/${locale}`);
    const versionFiles = fs.readdirSync(versionsDirectory)
      .map(file => file.replace('.md', ''))
      .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));

    return NextResponse.json({ versionFiles });
  } catch (error) {
    console.error('Error reading versions directory:', error);
    return NextResponse.json({ error: 'Error reading versions directory' }, { status: 500 });
  }
};
