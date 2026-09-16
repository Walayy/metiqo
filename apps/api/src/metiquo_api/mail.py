import smtplib
import ssl
from email.message import EmailMessage

from metiquo_api.auth_config import AuthSettings


def send_login_code(settings: AuthSettings, email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Votre code de connexion Metiquo"
    message["From"] = f"Metiquo <{settings.smtp_from}>"
    message["To"] = email
    message.set_content(
        f"Votre code Metiquo : {code}\n\n"
        "Saisissez ces 6 chiffres dans la fenêtre où vous avez demandé le code.\n"
        "Ce code est valable 10 minutes et ne peut être utilisé qu’une seule fois.\n"
        "Ne le partagez avec personne.\n\n"
        "Si vous n’êtes pas à l’origine de cette demande, ignorez cet email.\n"
        "Aucun compte n’est créé sans validation de votre adresse.\n\nMetiquo\n"
    )
    message.add_alternative(
        '<!doctype html><html lang="fr"><body style="margin:0;background:#f6f7f5;'
        'font-family:Arial,sans-serif;color:#242b25;padding:32px 16px">'
        '<main style="max-width:440px;margin:auto;background:#fff;border:1px solid #e4e8e1;'
        'border-radius:14px;padding:32px">'
        '<p style="font-size:22px;font-weight:700;margin:0 0 32px">metiquo.</p>'
        '<h1 style="font-size:24px">Votre accès à Metiquo</h1>'
        '<p style="line-height:1.6">Saisissez ce code dans la fenêtre où vous l’avez demandé.</p>'
        f'<p style="font-size:36px;letter-spacing:8px;font-weight:700;color:#387522;'
        f'background:#eef7e8;padding:24px 12px;text-align:center;border-radius:10px">{code}</p>'
        '<p style="line-height:1.6">Valable <strong>10 minutes</strong>, une seule fois. '
        "Ne partagez ce code avec personne.</p>"
        '<p style="font-size:12px;line-height:1.7;color:#657060;margin-top:32px">'
        "Vous n’avez pas demandé ce code ? Ignorez cet email. "
        "Aucun compte n’est créé sans validation de votre adresse.</p></main></body></html>",
        subtype="html",
    )
    smtp: smtplib.SMTP
    if settings.smtp_security == "tls":
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=10, context=ssl.create_default_context()
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
