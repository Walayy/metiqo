import { useState } from 'react';
import { ArrowUpRight, Check, Copy, HeartHandshake, Link } from 'lucide-react';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { config } from '@/lib/config';
import { supportLinks } from './links';
import './support.css';

type Kind = 'donation' | 'referral';
export function SupportDialog({ kind, onClose }: { kind: Kind | null; onClose: () => void }) {
  // Separate, stable content trees survive Radix's close animation without changing kind.
  return (
    <>
      {(['donation', 'referral'] as const).map((value) => (
        <SupportModal key={value} kind={value} open={kind === value} onClose={onClose} />
      ))}
    </>
  );
}
function SupportModal({ kind, open, onClose }: { kind: Kind; open: boolean; onClose: () => void }) {
  const donation = kind === 'donation';
  return (
    <Modal
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
      title={donation ? 'Soutenir Metiquo' : 'Parrainage Stake'}
      description={
        donation
          ? 'Un coup de pouce, à votre rythme.'
          : 'Soutenir le projet avec un lien de parrainage.'
      }
    >
      <SupportContent kind={kind} onClose={onClose} />
    </Modal>
  );
}
function SupportContent({ kind, onClose }: { kind: Kind; onClose: () => void }) {
  const donation = kind === 'donation';
  const url = supportLinks[kind];
  const [copyState, setCopyState] = useState('');
  async function copy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopyState('Lien copié.');
    } catch {
      setCopyState('Copie indisponible. Vous pouvez sélectionner le lien ci-dessus.');
    }
  }
  return (
    <div className="support-content">
      <span className="support-icon">
        {donation ? <HeartHandshake size={28} /> : <Link size={28} />}
      </span>
      <h3>
        {donation
          ? 'Un petit geste. Un projet qui avance.'
          : 'Votre soutien, en toute transparence.'}
      </h3>
      <p>
        {donation
          ? 'Vous appréciez Metiquo ? Un soutien volontaire aide à faire vivre le projet et à poursuivre son développement.'
          : 'Le parrainage est une autre façon de soutenir Metiquo. Le lien vous dirige vers Stake, où les conditions de l’offre sont présentées.'}
      </p>
      <ul className="support-points">
        {(donation
          ? [
              'Contribuer à l’hébergement et au traitement des données.',
              'Aider au développement des prochaines fonctionnalités.',
              'Un geste libre : les analyses restent accessibles sans don.',
            ]
          : [
              'Metiquo peut percevoir une rémunération liée au parrainage.',
              'Le parrainage n’influence ni les estimations ni les values.',
              'Aucun compte Stake n’est nécessaire pour consulter Metiquo.',
            ]
        ).map((text) => (
          <li key={text}>
            <Check size={15} />
            <span>{text}</span>
          </li>
        ))}
      </ul>
      {url ? (
        <>
          <div className="support-link-box">
            <span>{config.dataMode === 'mock' ? 'Lien temporaire' : 'Destination externe'}</span>
            <strong>{url}</strong>
          </div>
          <div className="support-actions">
            <a
              className="button button--primary"
              href={url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {donation ? 'Accéder au lien de soutien' : 'Voir le lien de parrainage'}
              <ArrowUpRight size={16} />
              <span className="sr-only"> (nouvel onglet)</span>
            </a>
            <Button onClick={() => void copy()}>
              <Copy size={15} />
              Copier le lien
            </Button>
          </div>
          <div className="support-copy-feedback" role="status">
            {copyState}
          </div>
        </>
      ) : (
        <>
          <p>
            Le lien sera disponible prochainement. Vous pouvez déjà faire découvrir Metiquo autour
            de vous.
          </p>
          <Button onClick={onClose}>Revenir à Metiquo</Button>
        </>
      )}
      <p className="support-disclosure">
        {config.dataMode === 'mock'
          ? 'Ce lien temporaire ouvre une page d’exemple. Aucun don, compte ni parrainage n’est créé.'
          : 'Vous quittez Metiquo en ouvrant ce lien. Aucune transaction n’est effectuée dans l’application.'}
        {!donation &&
          ' Réservé aux personnes majeures. Jouez avec modération ; le parrainage ne constitue pas un conseil de pari.'}
      </p>
    </div>
  );
}
