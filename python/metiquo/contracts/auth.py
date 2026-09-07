"""Etat public de connexion sans valeur de session ni empreinte privée."""

from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr

from metiquo.contracts.base import ContractModel


class OwnerIdentity(ContractModel):
    id: UUID
    username: str


class AuthStatus(ContractModel):
    mode: Literal["disabled", "owner"]
    authenticated: bool
    owner: OwnerIdentity | None = None


class OwnerLoginRequest(ContractModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)
