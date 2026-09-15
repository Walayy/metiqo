import { useState } from 'react';
import { clsx } from 'clsx';
interface Props {
  src: string;
  name: string;
  code?: string;
  className?: string;
  league?: boolean;
}
export function Logo({ src, name, code, className, league = false }: Props) {
  const [failed, setFailed] = useState(false);
  return (
    <span className={clsx('logo-frame', league && 'logo-frame--league', className)}>
      {src && !failed ? (
        <img
          src={src}
          alt={name}
          width={40}
          height={40}
          onError={() => setFailed(true)}
          loading="lazy"
          draggable={false}
        />
      ) : (
        <span role="img" aria-label={name}>
          {code ?? name.slice(0, 3)}
        </span>
      )}
    </span>
  );
}
