import { NextResponse } from 'next/server';

export async function GET() {
  const data = {
    message: 'This is system data',
    timestamp: new Date(),
  };
  return NextResponse.json(data, { status: 200 });
}

export async function POST() {
  // 如果需要在未来处理 POST 请求，可以在这里实现
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
}
