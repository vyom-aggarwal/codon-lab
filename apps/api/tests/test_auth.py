"""Token verification, and the forgeries it has to refuse.

Every test here mints a real token with a real key pair and presents it to
`auth.verify`. That matters: a test that stubbed the verifier would assert that
the stub works. The keys are generated in-process, so nothing is stored and
there is no fixture to keep in sync with a provider.

The four checks below are each individually sufficient to get in with a forged
token, so each gets a test that would pass if that check alone were dropped.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from codonlab import auth
from codonlab.config import get_settings

ISSUER = "https://codonlab-test.example.com/"
AUDIENCE = "codonlab-api"
KID = "test-key-1"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


#: One key pair for the whole module — generating RSA keys is slow and the tests
#: that need a *different* key make their own.
SIGNING_KEY = _key()
OTHER_KEY = _key()


def _jwks(key: rsa.RSAPrivateKey) -> dict[str, Any]:
    """The public half, in the JWKS shape a provider publishes."""
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}


class _StubJWKClient:
    """Stands in for the network call to the provider's JWKS endpoint.

    This is the *only* thing stubbed. Signature checking, expiry, issuer and
    audience are all done by the real PyJWT against real keys — the stub only
    avoids an HTTP request to a provider that does not exist.
    """

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._jwks = _jwks(key)

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return jwt.PyJWKSet.from_dict(self._jwks).keys[0]


def _token(
    *,
    key: rsa.RSAPrivateKey = SIGNING_KEY,
    subject: str = "auth0|scientist",
    issuer: str | None = ISSUER,
    audience: str | None = AUDIENCE,
    expires_in: timedelta = timedelta(minutes=30),
    **extra: Any,
) -> str:
    claims: dict[str, Any] = {
        "sub": subject,
        "exp": datetime.now(UTC) + expires_in,
        "iat": datetime.now(UTC),
        **extra,
    }
    if issuer is not None:
        claims["iss"] = issuer
    if audience is not None:
        claims["aud"] = audience
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in this module as a deployed, authenticating instance."""
    monkeypatch.setenv("CODONLAB_AUTH", "jwt")
    monkeypatch.setenv("CODONLAB_JWKS_URL", f"{ISSUER}.well-known/jwks.json")
    monkeypatch.setenv("CODONLAB_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("CODONLAB_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CORS_ORIGINS", "https://codon-lab.example.app")
    get_settings.cache_clear()
    auth._Keys.reset()
    auth._Keys.client = _StubJWKClient(SIGNING_KEY)  # type: ignore[assignment]
    yield
    get_settings.cache_clear()
    auth._Keys.reset()


def test_a_properly_signed_token_is_accepted() -> None:
    """The positive case. Without it every test below could pass by refusing
    everything, which is a broken API rather than a secure one."""
    claims = auth.verify(_token())
    assert claims["sub"] == "auth0|scientist"


def test_a_token_signed_by_the_wrong_key_is_refused() -> None:
    """The forgery that matters most: anybody can write the payload, so the
    signature is the only thing that makes it mean anything."""
    with pytest.raises(Exception) as raised:
        auth.verify(_token(key=OTHER_KEY))
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_an_expired_token_is_refused() -> None:
    """Without this a leaked token works forever."""
    with pytest.raises(Exception) as raised:
        auth.verify(_token(expires_in=timedelta(minutes=-5)))
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_a_token_from_another_issuer_is_refused() -> None:
    """A token minted by a different tenant of the same provider is correctly
    signed and unexpired. `iss` is the only thing separating them."""
    with pytest.raises(Exception) as raised:
        auth.verify(_token(issuer="https://someone-elses-tenant.example.com/"))
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_a_token_for_another_audience_is_refused() -> None:
    """The replay case. A token the same issuer minted for a *different*
    application of yours is signed, unexpired and from the right issuer — `aud`
    is what stops it being spent here."""
    with pytest.raises(Exception) as raised:
        auth.verify(_token(audience="some-other-api"))
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_a_token_with_no_expiry_is_refused() -> None:
    """`exp` is required, not merely checked when present. A token without one
    never expires, and omitting the claim must not be a way around the check."""
    with pytest.raises(Exception) as raised:
        auth.verify(_token(expires_in=timedelta(minutes=30), **{"exp": None}))
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_an_unsigned_token_is_refused() -> None:
    """`alg: none` is the textbook JWT attack: a token whose header declares it
    needs no signature. The algorithm allow-list is what refuses it."""
    forged = jwt.encode(
        {"sub": "auth0|attacker", "exp": datetime.now(UTC) + timedelta(hours=1)},
        key="",
        algorithm="none",
    )
    with pytest.raises(Exception) as raised:
        auth.verify(forged)
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_a_symmetrically_signed_token_is_refused() -> None:
    """The key-confusion attack: sign with HS256 using the *public* RSA key as
    the shared secret. A verifier that does not pin the algorithm family accepts
    it, because the public key is public — that is the whole point of it.

    The token is assembled by hand rather than with `jwt.encode`, because PyJWT
    refuses to *produce* one: it rejects a PEM as an HMAC secret. That guard is
    on the signing side and an attacker is not using PyJWT to sign. Building the
    three segments directly is what they would actually do, and it is the only
    way this test exercises the verifier rather than the encoder.
    """
    public_pem = SIGNING_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def segment(payload: dict[str, Any]) -> bytes:
        raw = json.dumps(payload, separators=(",", ":"), default=str).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = segment({"alg": "HS256", "typ": "JWT", "kid": KID})
    body = segment(
        {
            "sub": "auth0|attacker",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iss": ISSUER,
            "aud": AUDIENCE,
        }
    )
    signature = base64.urlsafe_b64encode(
        hmac.new(public_pem, header + b"." + body, hashlib.sha256).digest()
    ).rstrip(b"=")
    forged = b".".join((header, body, signature)).decode()

    with pytest.raises(Exception) as raised:
        auth.verify(forged)
    assert raised.value.status_code == 401  # type: ignore[attr-defined]


def test_the_refusal_never_says_which_check_failed() -> None:
    """Every rejection reads the same. Telling a caller that the signature was
    fine but the audience was wrong describes the token format to somebody
    probing it, and the real reason is in the platform's logs either way."""
    reasons = set()
    for token in (
        _token(key=OTHER_KEY),
        _token(expires_in=timedelta(minutes=-5)),
        _token(issuer="https://elsewhere.example.com/"),
        _token(audience="another-api"),
    ):
        with pytest.raises(Exception) as raised:
            auth.verify(token)
        reasons.add(str(raised.value.detail))  # type: ignore[attr-defined]
    assert len(reasons) == 1, f"refusals leak which check failed: {reasons}"


def test_the_jwks_document_is_a_real_one() -> None:
    """Sanity on the fixture itself: if `_jwks` produced something malformed,
    every refusal test above would pass for the wrong reason."""
    document = json.dumps(_jwks(SIGNING_KEY))
    assert '"kty": "RSA"' in document.replace('"kty":"RSA"', '"kty": "RSA"')


def test_the_algorithm_allow_list_admits_nothing_symmetric_or_unsigned() -> None:
    """Asserts the allow-list itself, not a behaviour that depends on it.

    The two forgery tests above pass even with `HS256` in the list, because a
    real JWKS hands back an RSA key object and the crypto layer refuses to use
    it as an HMAC secret. That refusal is incidental — it depends on the key
    type a provider happens to publish and on an implementation detail of
    PyJWT. The guarantee is that the decoder is never offered a symmetric or
    unsigned algorithm in the first place, and that is what this checks.

    Verified by mutation: widening `ALGORITHMS` to include HS256 and none leaves
    every other test in this file green. Only this one goes red.
    """
    for algorithm in auth.ALGORITHMS:
        assert algorithm != "none", "`none` means an unsigned token is accepted"
        assert not algorithm.startswith("HS"), (
            f"{algorithm} is symmetric: a token signed with the provider's own public "
            f"key would verify, and that key is public"
        )
    assert auth.ALGORITHMS, "an empty allow-list refuses every valid token too"
