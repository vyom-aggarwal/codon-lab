"""Authentication: verifying who is calling, and refusing when it cannot be known.

This module has one job — turn an ``Authorization: Bearer <token>`` header into
a ``User`` row, or refuse the request. It never issues a token, never stores a
credential, and never trusts a claim it has not cryptographically verified.

**Why a provider rather than passwords.** See ``models/identity``. The short
version: this product holds unpublished protein sequences, and every part of
password handling that could be got wrong is delegated to a service whose
business is getting it right.

**What "verify" has to mean.** The dangerous way to read a JWT is to decode it
and trust the payload — the format is three base64 segments and the third one is
the only thing stopping anybody from writing their own. Verification here is
strict on all four of the things that are individually sufficient to forge
access:

  signature   against the provider's published key, fetched from JWKS
  ``exp``     so a leaked token stops working
  ``iss``     so a token from a *different* tenant of the same provider is not
              accepted here
  ``aud``     so a token minted for another application of the same issuer is
              not replayed against this one

PyJWT does all four, and is asked to do all four explicitly. Nothing here parses
a token by hand.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from sqlmodel import Session, select

from codonlab.config import get_settings
from codonlab.db import get_session
from codonlab.models import User

#: The local, unauthenticated identity. When CODONLAB_AUTH is `disabled` every
#: request resolves to this one user, so the ownership rules below run exactly
#: as they do in production rather than being bypassed by a separate code path.
#: A permission check that is skipped locally is a permission check nobody has
#: ever run.
#:
#: The UUID is fixed rather than random so a developer's projects survive a
#: restart. config.py refuses to start in this mode once CORS_ORIGINS names a
#: non-local origin, which is what stops it reaching a deployment.
#: The signature algorithms this service will accept.
#:
#: Asymmetric only, and that is the security property rather than a preference.
#: `none` declares a token needs no signature at all. The `HS*` family is worse
#: in practice: it is *symmetric*, so a verifier that accepts it can be handed a
#: token signed with the provider's own **public** key as the shared secret —
#: which is public by definition. Both are refused here by never being offered
#: to the decoder.
#:
#: `tests/test_auth.py` asserts this list directly. It has to: with a real JWKS
#: the key-confusion attack also fails on a key-type mismatch inside the crypto
#: layer, so a behavioural test alone passes even when the allow-list is wrong.
#: That incidental protection is not the guarantee — this tuple is.
ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384")

LOCAL_SUBJECT = "local-development"
LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _Keys:
    """The JWKS client, built once.

    Kept behind a module-level holder rather than an ``lru_cache`` on a function
    because ``PyJWKClient`` maintains its own key cache and handles rotation: a
    provider that rolls its signing key publishes both for an overlap period,
    and a client rebuilt per request would refetch the key set on every single
    call — turning the identity provider into a hard dependency of throughput.
    """

    client: PyJWKClient | None = None

    @classmethod
    def get(cls, url: str) -> PyJWKClient:
        if cls.client is None:
            cls.client = PyJWKClient(url, cache_keys=True)
        return cls.client

    @classmethod
    def reset(cls) -> None:
        """Test seam. Never called in production."""
        cls.client = None


def _unauthorised(detail: str) -> HTTPException:
    # 401 with the challenge header, not 403: the caller has not proven who they
    # are, which is a different failure from proving it and being refused.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify(token: str) -> dict[str, Any]:
    """Decode a token, or raise. The claims returned have been verified.

    Every failure is reported as the same 401 with a generic reason. Telling a
    caller *which* check failed — bad signature versus wrong audience versus
    expired — is a description of the token format that only helps somebody
    probing it; the real reason is logged by the platform, not returned.
    """
    settings = get_settings()
    if not settings.jwks_url:  # pragma: no cover - config guard already refuses
        raise _unauthorised("The API is not configured to verify tokens.")

    try:
        signing_key = _Keys.get(settings.jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=list(ALGORITHMS),
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                # Only require what is actually checked. `aud` and `iss` become
                # required exactly when they are configured, so an instance that
                # sets them cannot be handed a token that simply omits them.
                "require": ["exp", "sub"],
                "verify_aud": settings.jwt_audience is not None,
                "verify_iss": settings.jwt_issuer is not None,
            },
        )
    except jwt.PyJWTError as error:
        raise _unauthorised("The access token is not valid.") from error
    except Exception as error:
        # Anything that is not a PyJWT error is still a token this service could
        # not verify, and the only safe response to that is the same refusal.
        #
        # Not defensive padding: a token whose header names a symmetric
        # algorithm while the JWKS supplies an RSA key raises `TypeError` out of
        # the crypto layer, below PyJWT's own exception hierarchy. Caught only
        # as `PyJWTError`, that escapes as a 500 with a stack trace — turning a
        # forged token into an information leak and an error-rate spike, which
        # is a worse outcome than the 401 it should always have been.
        #
        # Found by mutation-testing the algorithm allow-list, not by reasoning.
        raise _unauthorised("The access token is not valid.") from error


def _user_for(session: Session, *, subject: str, claims: dict[str, Any]) -> User:
    """Find this subject's row, creating it the first time they appear.

    First sight creates the row because the identity provider has already
    established who this is. A separate registration step would be a form asking
    a scientist to confirm what they just signed in as.
    """
    existing = session.exec(select(User).where(User.subject == subject)).first()
    if existing is not None:
        # Display fields are refreshed from the token: someone who changes their
        # name at the provider should not see a stale one here. `subject` is
        # never updated — it is the identity.
        email = claims.get("email")
        name = claims.get("name") or claims.get("nickname")
        if email != existing.email or name != existing.display_name:
            existing.email = email
            existing.display_name = name
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing

    created = User(
        subject=subject,
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("nickname"),
    )
    session.add(created)
    session.commit()
    session.refresh(created)
    return created


def _local_user(session: Session) -> User:
    """The single implicit user for unauthenticated local development."""
    existing = session.exec(select(User).where(User.subject == LOCAL_SUBJECT)).first()
    if existing is not None:
        return existing
    created = User(id=LOCAL_USER_ID, subject=LOCAL_SUBJECT, display_name="Local development")
    session.add(created)
    session.commit()
    session.refresh(created)
    return created


def current_user(
    session: Session = Depends(get_session),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """The caller, as a ``User`` row. Raises 401 when they cannot be identified.

    This is the only way a route learns who is calling. It returns a row rather
    than a subject string so that ownership is a foreign key comparison rather
    than a string comparison repeated in twenty places.
    """
    settings = get_settings()
    if not settings.auth_required:
        return _local_user(session)

    if not authorization:
        raise _unauthorised("This endpoint requires an access token.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorised("Expected an 'Authorization: Bearer <token>' header.")

    claims = verify(token)
    subject = claims.get("sub")
    if not subject:
        # `require: ["sub"]` above means PyJWT has already rejected this, but a
        # token whose subject is present and empty would otherwise create a user
        # keyed on the empty string — one row that every such caller shares.
        raise _unauthorised("The access token carries no subject.")
    return _user_for(session, subject=str(subject), claims=claims)


CurrentUser = Annotated[User, Depends(current_user)]
