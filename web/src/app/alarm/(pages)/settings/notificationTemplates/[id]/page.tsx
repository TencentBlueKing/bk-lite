import TemplateEditor from '../components/templateEditor';

export default async function EditNotificationTemplatePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TemplateEditor templateId={id} />;
}
