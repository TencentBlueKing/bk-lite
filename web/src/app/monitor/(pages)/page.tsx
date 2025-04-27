'use client';
import { redirect } from 'next/navigation';

export default function HomePage() {
  redirect('/monitor/search');
  return null;
}
