import { Database, Layers3 } from 'lucide-react';
import './source-mark.css';

/** Local sourced marks; descriptive icons for sources without a verified logo. */
export function SourceMark({
  source,
  decorative = false,
}: {
  source: string;
  decorative?: boolean;
}) {
  if (source === 'LoL' || source === 'lol-catalog')
    return <img className="source-mark" src="/games/lol.svg" alt="" width={24} height={24} />;
  if (source === 'Stake' || source === 'stake-markets' || source === 'settle-selections')
    return (
      <span
        className="source-mark source-mark--stake"
        role="img"
        aria-label="Stake"
        aria-hidden={decorative || undefined}
      />
    );
  if (source === 'loltv-matches')
    return (
      <span
        className="source-mark source-mark--loltv"
        role="img"
        aria-label="LoLTV"
        aria-hidden={decorative || undefined}
      />
    );
  const Icon = source.startsWith('oracle') || source === 'Oracle’s Elixir' ? Database : Layers3;
  return <Icon className="source-mark" size={22} aria-hidden="true" />;
}
