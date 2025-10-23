'use client';
import { redirect } from "next/navigation";

export default function HomePage() {
  return redirect('/lab/mirror');
}