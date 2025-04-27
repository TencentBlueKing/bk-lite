'use client';
import { redirect } from 'next/navigation';

export default function HomePage() {
  redirect('/system-manager/userspage');
  return null;
}