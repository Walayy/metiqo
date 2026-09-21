import { useState } from 'react';
import { clsx } from 'clsx';
import { Shield, Trophy } from 'lucide-react';
interface Props {
  src: string;
  name: string;
  code?: string;
  className?: string;
  league?: boolean;
}
export function Logo({ src, name, className, league = false }: Props) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const Fallback = league ? Trophy : Shield;
  return (
    <span className={clsx('logo-frame', league && 'logo-frame--league', className)}>
      {src && failedSrc !== src ? (
        <img
          src={src}
          alt={name}
          width={40}
          height={40}
          onError={() => setFailedSrc(src)}
          loading="lazy"
          draggable={false}
        />
      ) : (
        <span className="logo-fallback" role="img" aria-label={`${name} — logo indisponible`}>
          <Fallback aria-hidden="true" size={22} strokeWidth={1.5} />
        </span>
      )}
    </span>
  );
}
