import { useContext, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, Check, LogOut, Mail, ShieldCheck, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Spinner } from '@/components/ui/spinner';
import { FieldFeedback } from '@/components/ui/field-feedback';
import { accountDate } from '@/lib/format';
import { AuthError, logout, requestCode, sessionQuery, verifyCode } from './api';
import { codeSchema, emailSchema } from './contracts';
import type { AuthSession, Challenge } from './contracts';
import './auth.css';
import { authFeedbackMessages, authMessages } from './messages';
import { AccountContext } from './account-context';
import { StatusPanel } from '@/features/status/status-panel';
import { HttpError } from '@/lib/http-error';
import { requestCooldown } from '@/lib/http';

export function Account() {
  const session = useQuery(sessionQuery);
  const client = useQueryClient();
  const account = useContext(AccountContext);
  if (!account) throw new Error('Account requires its dialog context');
  const { open, setOpen } = account;
  const channel = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    if (!('BroadcastChannel' in window)) return;
    const connection = new BroadcastChannel('metiquo-auth');
    channel.current = connection;
    connection.onmessage = () => {
      void client.invalidateQueries({ queryKey: sessionQuery.queryKey });
    };
    return () => {
      channel.current = null;
      connection.close();
    };
  }, [client]);
  async function updateSession(next: AuthSession) {
    await client.cancelQueries({ queryKey: sessionQuery.queryKey });
    client.setQueryData(sessionQuery.queryKey, next);
    channel.current?.postMessage('session-changed');
  }
  const user = session.data?.user;
  return (
    <>
      <Button
        className="account-trigger"
        variant={user ? 'secondary' : 'primary'}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={user ? 'Afficher mon profil' : 'Se connecter ou s’inscrire'}
      >
        {session.isPending ? <Spinner /> : <UserRound size={16} />}
        <span>{user ? 'Mon profil' : 'Se connecter'}</span>
      </Button>
      {open && (
        <AccountDialog
          session={session.data}
          loading={session.isPending}
          retrying={session.isFetching}
          failure={session.error}
          retry={() => {
            void session.refetch();
          }}
          onClose={() => setOpen(false)}
          onSession={updateSession}
        />
      )}
    </>
  );
}

interface Props {
  session: AuthSession | undefined;
  loading: boolean;
  retrying: boolean;
  failure: Error | null;
  retry: () => void;
  onClose: () => void;
  onSession: (session: AuthSession) => Promise<void>;
}

function AccountDialog({ session, loading, retrying, failure, retry, onClose, onSession }: Props) {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [notice, setNotice] = useState('');
  const [now, setNow] = useState(Date.now);
  const [blockedUntil, setBlockedUntil] = useState(0);
  const [serviceFailure, setServiceFailure] = useState<HttpError | null>(() =>
    requestCooldown('/api/v1/auth/request-code'),
  );
  const emailInput = useRef<HTMLInputElement>(null);
  const codeInput = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const sending = useRef(false);
  const user = session?.user;
  const validationError = challenge
    ? !code
      ? authMessages.codeRequired
      : !codeSchema.safeParse(code).success
        ? authMessages.codeIncomplete
        : ''
    : !email.trim()
      ? authMessages.emailRequired
      : !emailSchema.safeParse(email.trim()).success
        ? authMessages.emailInvalid
        : '';
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!challenge && !blockedUntil) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge, blockedUntil]);
  useEffect(() => {
    if (challenge) codeInput.current?.focus();
  }, [challenge]);

  const action = useMutation({
    retry: false,
    mutationFn: async ({
      kind,
      verificationCode,
    }: {
      kind: 'send' | 'verify' | 'logout';
      verificationCode?: string;
    }) => {
      controller.current?.abort();
      const pending = new AbortController();
      controller.current = pending;
      setError('');
      setNotice('');
      if (kind === 'send') {
        const address = emailSchema.safeParse(email.trim());
        if (!address.success) throw new AuthError(authMessages.emailInvalid);
        const result = await requestCode(address.data, pending.signal);
        if (pending.signal.aborted) return;
        setEmail(address.data);
        setChallenge(result);
        setCode('');
        setSubmitted(false);
        setNow(Date.now());
        setNotice(challenge ? authMessages.codeResent : '');
      } else if (kind === 'verify' && challenge) {
        const parsed = codeSchema.safeParse(verificationCode);
        if (!parsed.success) throw new AuthError(authMessages.codeIncomplete);
        const result = await verifyCode(challenge.challengeId, parsed.data, pending.signal);
        if (pending.signal.aborted) return;
        await onSession(result);
        setChallenge(null);
        setCode('');
        setSubmitted(false);
        setNotice(authMessages.signedIn);
      } else if (kind === 'logout') {
        await logout(pending.signal);
        if (pending.signal.aborted) return;
        await onSession({ user: null, expiresAt: null });
        setChallenge(null);
        onClose();
      }
    },
    onSettled: () => {
      sending.current = false;
    },
    onError: (failure) => {
      if (controller.current?.signal.aborted) return;
      if (
        failure instanceof HttpError &&
        ![400, 403, 422].includes(failure.status) &&
        !(failure instanceof AuthError && failure.status === 0)
      ) {
        setServiceFailure(failure);
      } else {
        setError(failure instanceof HttpError ? failure.message : authMessages.failed);
      }
      if (failure instanceof HttpError && failure.retryAt) {
        setBlockedUntil(failure.retryAt);
        setNow(Date.now());
      }
      if (challenge) {
        codeInput.current?.focus();
        codeInput.current?.select();
      } else emailInput.current?.focus();
    },
  });
  const resendSeconds = Math.max(
    0,
    Math.ceil(
      (Math.max(challenge ? Date.parse(challenge.resendAt) : 0, blockedUntil) - now) / 1000,
    ),
  );
  const expired = challenge ? now >= Date.parse(challenge.expiresAt) : false;
  const fieldError = expired
    ? authMessages.codeExpired
    : error || (submitted ? validationError : '');
  const fieldHint = challenge
    ? authMessages.codeHint
    : resendSeconds > 0
      ? `Nouvel envoi possible dans ${resendSeconds} s.`
      : authMessages.emailHint;
  const fieldMessage = fieldError || notice || fieldHint;
  const fieldTone = fieldError ? 'error' : notice ? 'success' : 'hint';
  function startAction(kind: 'send' | 'verify' | 'logout', verificationCode = code) {
    if (sending.current || action.isPending) return;
    const currentTime = Date.now();
    if (
      kind === 'verify' &&
      (!challenge ||
        currentTime >= Date.parse(challenge.expiresAt) ||
        blockedUntil > currentTime ||
        !codeSchema.safeParse(verificationCode).success)
    )
      return;
    if (
      kind === 'send' &&
      Math.max(challenge ? Date.parse(challenge.resendAt) : 0, blockedUntil) > currentTime
    )
      return;
    sending.current = true;
    action.mutate({ kind, verificationCode: kind === 'verify' ? verificationCode : undefined });
  }
  function changeCode(value: string) {
    if (sending.current) return;
    const next = value.replace(/\D/g, '').slice(0, 6);
    setCode(next);
    setError('');
    setNotice('');
    if (next.length === 6 && next !== code) {
      setSubmitted(true);
      startAction('verify', next);
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (action.isPending || expired || (challenge ? blockedUntil > now : resendSeconds > 0)) return;
    setSubmitted(true);
    setError('');
    setNotice('');
    if (validationError) {
      (challenge ? codeInput : emailInput).current?.focus({ preventScroll: true });
      return;
    }
    startAction(challenge ? 'verify' : 'send');
  }
  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={
        failure || serviceFailure
          ? 'Votre connexion à Metiquo'
          : user
            ? 'Votre profil'
            : challenge
              ? 'Consultez votre boîte mail'
              : 'Bienvenue sur Metiquo'
      }
      description={
        failure || serviceFailure
          ? 'Les informations pour poursuivre.'
          : user
            ? 'Votre compte, en toute simplicité.'
            : challenge
              ? 'Un code à 6 chiffres vous attend pour continuer.'
              : 'Connectez-vous ou créez votre compte avec votre email.'
      }
      initialFocusRef={emailInput}
      className="auth-modal"
    >
      <div className="auth-body" aria-busy={loading || action.isPending}>
        {loading ? (
          <div className="auth-loading" role="status">
            <Spinner /> Vérification de votre session…
          </div>
        ) : failure || serviceFailure ? (
          <StatusPanel
            compact
            error={failure ?? serviceFailure!}
            busy={retrying}
            onRetry={
              failure
                ? retry
                : () => {
                    setServiceFailure(null);
                    requestAnimationFrame(() =>
                      (challenge ? codeInput : emailInput).current?.focus(),
                    );
                  }
            }
            retryLabel={failure ? 'Vérifier ma session' : 'Reprendre'}
          />
        ) : user ? (
          <>
            <div className="auth-profile-heading">
              <span className="auth-emblem">
                <UserRound size={24} />
              </span>
              <div>
                <strong>Votre espace Metiquo</strong>
                <span className="auth-role">
                  {user.role === 'admin' ? (
                    <>
                      <ShieldCheck size={13} /> Administrateur
                    </>
                  ) : (
                    'Utilisateur'
                  )}
                </span>
              </div>
            </div>
            <dl className="auth-profile-details">
              <div>
                <dt>Adresse email</dt>
                <dd>
                  {user.email}
                  <span className="auth-verified">
                    <Check size={13} /> Vérifiée
                  </span>
                </dd>
              </div>
              <div>
                <dt>Membre depuis le</dt>
                <dd>{accountDate(user.createdAt)}</dd>
              </div>
            </dl>
            <FieldFeedback
              id="auth-profile-feedback"
              message={error || notice}
              tone={error ? 'error' : 'success'}
              reserve={authFeedbackMessages}
            />
            <Button
              onClick={() => startAction('logout')}
              disabled={action.isPending}
              className="auth-submit"
            >
              {action.isPending ? <Spinner /> : <LogOut size={16} />}{' '}
              {action.isPending ? 'Déconnexion…' : 'Se déconnecter'}
            </Button>
          </>
        ) : (
          <>
            <div className="auth-intro">
              <span className="auth-emblem">
                <Mail size={23} />
              </span>
              <div>
                <strong>{challenge ? email : 'Un email. Un code. Vous y êtes.'}</strong>
                <p>
                  {challenge
                    ? 'Utilisez le dernier code reçu, dans cette fenêtre.'
                    : 'Aucun mot de passe à retenir.'}
                </p>
              </div>
            </div>
            <form noValidate onSubmit={submit} className="auth-form">
              {challenge ? (
                <div className="auth-field">
                  <label htmlFor="auth-code">Code de vérification</label>
                  <input
                    ref={codeInput}
                    id="auth-code"
                    className="auth-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    minLength={6}
                    required
                    value={code}
                    onChange={(event) => changeCode(event.target.value)}
                    onPaste={(event) => {
                      event.preventDefault();
                      changeCode(event.clipboardData.getData('text'));
                    }}
                    placeholder="000000"
                    aria-invalid={!!fieldError}
                    aria-describedby="auth-code-feedback"
                    readOnly={action.isPending}
                  />
                  <FieldFeedback
                    id="auth-code-feedback"
                    message={fieldMessage}
                    tone={fieldTone}
                    reserve={authFeedbackMessages}
                  />
                </div>
              ) : (
                <div className="auth-field">
                  <label htmlFor="auth-email">Adresse email</label>
                  <input
                    ref={emailInput}
                    id="auth-email"
                    type="email"
                    autoComplete="email"
                    inputMode="email"
                    autoCapitalize="none"
                    spellCheck={false}
                    maxLength={254}
                    required
                    placeholder="vous@exemple.fr"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setError('');
                    }}
                    readOnly={action.isPending}
                    aria-invalid={!!fieldError}
                    aria-describedby="auth-email-feedback"
                  />
                  <FieldFeedback
                    id="auth-email-feedback"
                    message={fieldMessage}
                    tone={fieldTone}
                    reserve={authFeedbackMessages}
                  />
                </div>
              )}
              <Button
                type="submit"
                variant="primary"
                className="auth-submit"
                disabled={
                  action.isPending ||
                  (challenge ? expired || blockedUntil > now : resendSeconds > 0)
                }
              >
                {action.isPending ? (
                  <Spinner />
                ) : challenge ? (
                  <Check size={17} />
                ) : (
                  <ArrowRight size={17} />
                )}
                {action.isPending
                  ? action.variables?.kind === 'send'
                    ? 'Envoi du code…'
                    : 'Vérification…'
                  : challenge
                    ? 'Se connecter'
                    : 'Recevoir mon code'}
              </Button>
            </form>
            {challenge ? (
              <div className="auth-secondary-actions">
                <Button
                  variant="ghost"
                  disabled={action.isPending || resendSeconds > 0}
                  onClick={() => startAction('send')}
                >
                  {resendSeconds > 0 ? `Renvoyer dans ${resendSeconds} s` : 'Renvoyer un code'}
                </Button>
                <Button
                  variant="ghost"
                  disabled={action.isPending}
                  onClick={() => {
                    setChallenge(null);
                    setCode('');
                    setSubmitted(false);
                    setError('');
                    setNotice('');
                    requestAnimationFrame(() => emailInput.current?.focus());
                  }}
                >
                  <ArrowLeft size={14} /> Modifier l’email
                </Button>
              </div>
            ) : null}
            <div className="auth-security">
              <ShieldCheck size={16} />
              <p>
                {challenge
                  ? 'Pensez aussi à vérifier vos courriers indésirables.'
                  : 'Seul l’accès à votre boîte mail permet de vous connecter.'}
              </p>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
