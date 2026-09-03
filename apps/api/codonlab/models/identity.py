"""Who is using this instance.

The scope of this module is deliberately small, and the shape of what it is
*not* matters as much as what it is.

**There are no credentials here.** No password hash, no reset token, no session
table. Identity is asserted by an OIDC provider — Clerk, Auth0, Supabase,
WorkOS, Firebase, Okta, any of them — and this service only ever *verifies* a
signed token against that provider's published keys. Password storage, reset
flows, email verification, lockout, MFA: each is a place to get security wrong,
and a tool holding unpublished protein sequences does not get to be casual about
that. Unpublished sequence is intellectual property; a lab's design set before
publication is the most sensitive thing this product touches.

**A user, not yet an organisation.** Labs collaborate, and eventually a project
will belong to a group rather than a person. That needs invitations, roles and a
sharing UI, which is a feature rather than a column. The schema is shaped so it
can arrive without a rewrite: ownership already hangs off a single foreign key
on ``Project``, so an ``Organisation`` slots between ``User`` and ``Project``
without touching anything downstream. Every target, run, score and measurement
reaches its owner through ``project_id`` and stays untouched either way.
"""

from __future__ import annotations

from sqlmodel import Field

from codonlab.models.base import TimestampedModel


class User(TimestampedModel, table=True):
    """One row per identity that has ever presented a valid token.

    Created on first sight rather than by a registration flow: the provider has
    already established who this is, and a second sign-up step would be a form
    that asks a scientist to confirm what the identity provider just asserted.
    """

    #: The `sub` claim — the provider's stable, unique identifier for this
    #: person. Unique and indexed because it is the lookup key on every single
    #: authenticated request, and because two rows for one subject would split a
    #: researcher's projects in half with no way to tell from the interface.
    #:
    #: Deliberately not the email address. Emails get reassigned when someone
    #: leaves an institution, and a returning address must not inherit the
    #: previous holder's unpublished work.
    subject: str = Field(index=True, unique=True, nullable=False)

    #: Shown in the interface so a person can tell whose instance they are on.
    #: Nullable because the `email` claim is a provider option rather than a
    #: guarantee, and an account that cannot display a friendly name is a
    #: cosmetic problem, not a reason to refuse a valid token.
    email: str | None = Field(default=None, index=True)

    #: Also cosmetic, also optional, also never used to identify anybody.
    display_name: str | None = Field(default=None)
