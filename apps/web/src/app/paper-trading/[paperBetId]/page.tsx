import { PaperBetDetail } from "../../../components/paper-bet-detail";

type PaperBetDetailPageProperties = Readonly<{
  params: Promise<Readonly<{ paperBetId: string }>>;
}>;

export default async function PaperBetDetailPage({ params }: PaperBetDetailPageProperties) {
  const { paperBetId } = await params;
  return <PaperBetDetail paperBetId={paperBetId} />;
}
