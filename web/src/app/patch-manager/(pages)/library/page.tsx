import { redirect } from 'next/navigation';
import { getLibraryRoute } from './_components/library-routes';

export default function LibraryPage() {
  redirect(getLibraryRoute('win'));
}
