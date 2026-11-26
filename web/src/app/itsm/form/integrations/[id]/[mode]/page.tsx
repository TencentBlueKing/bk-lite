'use client';
import { useParams } from 'next/navigation';
import Workspace from '../../workspace';
export default function Page(){const {id,mode}=useParams<{id:string;mode:string}>();return <Workspace integrationId={id} mode={mode} />;}
