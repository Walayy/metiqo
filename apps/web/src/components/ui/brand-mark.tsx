import type { CSSProperties } from 'react';

const resolutions = [32, 64, 128, 256];
function sources(theme: string, format: string) {
  return resolutions.map((size) => `/brand/${theme}/mark-${size}.${format} ${size}w`).join(', ');
}

/** Brand assets stay separate from sourced team and competition logos. */
export function BrandMark({ size = 40 }: { size?: 28 | 40 | 80 }) {
  return (
    <span
      className="brand-mark"
      aria-hidden="true"
      style={{ '--brand-mark-size': `${size}px` } as CSSProperties}
    >
      {(['light', 'dark'] as const).map((theme) => (
        <picture className={`brand-${theme}`} key={theme}>
          <source type="image/webp" srcSet={sources(theme, 'webp')} sizes={`${size}px`} />
          <img
            src={`/brand/${theme}/mark-64.png`}
            srcSet={sources(theme, 'png')}
            sizes={`${size}px`}
            width={size}
            height={size}
            alt=""
            decoding="async"
          />
        </picture>
      ))}
    </span>
  );
}
