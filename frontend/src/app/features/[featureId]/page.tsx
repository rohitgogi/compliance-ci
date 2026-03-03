import FeatureDetailContent from "@/components/pages/FeatureDetailContent";

export default async function FeatureDetailPage({
  params,
}: {
  params: Promise<{ featureId: string }>;
}) {
  const { featureId } = await params;
  return <FeatureDetailContent featureId={featureId} />;
}
