export const authMessages = {
  emailRequired: 'Saisissez votre adresse email.',
  emailInvalid: 'Saisissez une adresse email valide.',
  emailHint: 'Votre première connexion crée automatiquement votre compte.',
  codeRequired: 'Saisissez le code reçu par email.',
  codeIncomplete: 'Le code doit contenir 6 chiffres.',
  codeInvalid: 'Code incorrect ou expiré. Vérifiez-le ou demandez-en un nouveau.',
  codeExpired: 'Ce code a expiré. Demandez-en un nouveau.',
  codeHint: 'Connexion automatique au 6e chiffre. Code valable 10 minutes.',
  codeResent: 'Un nouveau code vient de vous être envoyé.',
  signedIn: 'Vous êtes connecté. Bienvenue sur Metiquo.',
  offline: 'Connexion au serveur impossible. Veuillez réessayer.',
  refused: 'Demande refusée. Rechargez la page et réessayez.',
  invalidRequest: 'Vérifiez votre adresse email et les 6 chiffres du code.',
  rateLimited: 'Trop de demandes. Patientez avant de réessayer.',
  unavailable: 'Service de connexion indisponible. Réessayez dans un moment.',
  invalidResponse: 'Réponse du serveur invalide. Veuillez réessayer.',
  failed: 'La demande a échoué. Veuillez réessayer.',
} as const;

export const authFeedbackMessages = [
  ...Object.values(authMessages),
  'Nouvel envoi possible dans 3600 s.',
];
