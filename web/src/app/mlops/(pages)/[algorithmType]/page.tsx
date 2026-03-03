'use client';

import { redirect } from 'next/navigation';
import { useParams } from 'next/navigation';

export default function AlgorithmTypePage() {
  const params = useParams();
  const algorithmType = params.algorithmType as string;
  
  redirect(`/mlops/${algorithmType}/datasets`);
}
