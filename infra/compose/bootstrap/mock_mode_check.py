"""Garde one-shot du profil Compose mock."""

from metiquo.config import DataMode, load_settings


def main() -> None:
    """Refuser le profil mock si la configuration demande des données réelles."""

    if load_settings().app_data_mode is not DataMode.MOCK:
        raise SystemExit("Le profil Compose mock exige APP_DATA_MODE=mock")


if __name__ == "__main__":
    main()
