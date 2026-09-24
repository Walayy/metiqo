import { HttpError } from '@/lib/http-error';
import { isAppView } from '@/app/navigation';

export function statusContent(error: Error) {
  const failure = error instanceof HttpError ? error : new HttpError(0, { kind: 'unexpected' });
  const { status, kind } = failure;
  if (kind === 'network')
    return {
      code: 'Connexion',
      title: 'La connexion est interrompue.',
      description:
        'Impossible de joindre Metiquo. Vérifiez votre connexion internet, puis réessayez.',
      icon: 'network',
      action: 'retry',
    } as const;
  if (kind === 'timeout')
    return {
      code: 'Délai dépassé',
      title: 'La réponse se fait attendre.',
      description: 'La demande a pris trop de temps. Vous pouvez réessayer dans un moment.',
      icon: 'clock',
      action: 'retry',
    } as const;
  if (kind === 'invalid-response')
    return {
      code: 'Données indisponibles',
      title: 'Les données sont incomplètes.',
      description:
        'La réponse reçue ne permet pas d’afficher des informations fiables. Réessayez dans un moment.',
      icon: 'server',
      action: 'retry',
    } as const;
  const content = {
    400: {
      title: 'La demande ne peut pas aboutir.',
      description: failure.message,
      icon: 'document',
      action: 'home',
    },
    401: {
      title: 'Une connexion est nécessaire.',
      description:
        'Votre session a expiré ou vous n’êtes pas connecté. Connectez-vous pour poursuivre ici.',
      icon: 'lock',
      action: 'login',
    },
    403: {
      title: 'Cet espace est réservé.',
      description:
        'Votre compte ne dispose pas des droits nécessaires. Vous pouvez continuer à consulter les matchs.',
      icon: 'shield',
      action: 'home',
    },
    404: {
      title: 'Cette page est introuvable.',
      description:
        'Ce lien est incorrect ou ce contenu n’est plus disponible. Retrouvez votre chemin depuis les matchs.',
      icon: 'document',
      action: 'home',
    },
    408: {
      title: 'La réponse se fait attendre.',
      description: failure.message,
      icon: 'clock',
      action: 'retry',
    },
    409: {
      title: 'Les informations ont changé.',
      description:
        'Une autre modification ou une action en cours empêche cette demande. Actualisez les informations avant de recommencer.',
      icon: 'refresh',
      action: 'retry',
    },
    410: {
      title: 'Ce contenu n’est plus disponible.',
      description:
        'Il a été retiré des données accessibles. Retrouvez les opportunités disponibles depuis les values.',
      icon: 'document',
      action: 'home',
    },
    413: {
      title: 'La demande est trop volumineuse.',
      description: failure.message,
      icon: 'document',
      action: 'home',
    },
    422: {
      title: 'Quelques informations sont à corriger.',
      description: failure.message,
      icon: 'document',
      action: 'home',
    },
    423: {
      title: 'Ce compte est suspendu.',
      description:
        'L’accès à ce compte a été suspendu. Seul un administrateur de Metiquo peut le rétablir ; patienter ou demander un nouveau code ne le débloquera pas.',
      icon: 'lock',
      action: 'home',
    },
    429: {
      title: 'Un instant, s’il vous plaît.',
      description:
        'Trop de demandes ont été envoyées en peu de temps. Une courte pause est nécessaire avant de reprendre.',
      icon: 'clock',
      action: 'retry',
    },
    500: {
      title: 'Un contretemps côté serveur.',
      description: 'Metiquo n’a pas pu terminer votre demande. Réessayez dans un moment.',
      icon: 'server',
      action: 'retry',
    },
    502: {
      title: 'Le serveur est injoignable.',
      description: 'La communication avec le serveur est interrompue. Réessayez dans un moment.',
      icon: 'server',
      action: 'retry',
    },
    503: {
      title: 'Le service fait une pause.',
      description: 'Cette partie de Metiquo est momentanément indisponible. Réessayez plus tard.',
      icon: 'server',
      action: 'retry',
    },
    504: {
      title: 'Le serveur met trop de temps.',
      description: 'La réponse n’est pas arrivée à temps. Vous pouvez réessayer dans un moment.',
      icon: 'clock',
      action: 'retry',
    },
  } as const;
  return status in content
    ? { code: String(status), ...content[status as keyof typeof content] }
    : ({
        code: 'Erreur inattendue',
        title: 'Cet écran a rencontré un problème.',
        description: 'Metiquo n’a pas pu afficher cet écran. Rechargez-le pour repartir.',
        icon: 'server',
        action: 'retry',
      } as const);
}

export function isKnownLocation(pathname: string, search: string) {
  const view = new URLSearchParams(search).get('view');
  return pathname === '/' && (view === null || view === '' || isAppView(view));
}

export function waitLabel(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours
    ? `${hours} h ${String(minutes).padStart(2, '0')} min`
    : minutes
      ? `${minutes} min ${String(rest).padStart(2, '0')} s`
      : `${rest} s`;
}
