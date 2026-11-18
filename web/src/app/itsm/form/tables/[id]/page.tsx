'use client';
import { useParams } from 'next/navigation';
import Workspace from '../workspace';
export default function Page(){const {id}=useParams<{id:string}>();return <Workspace tableId={Number(id)} />;}
