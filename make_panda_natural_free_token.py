#!/usr/bin/env python3
"""Issue a Panda test token that always selects a natural free-spin package.

The source token must be a currently valid Panda player token for the intended
test account.  Its account/session fields are preserved, so this tool does not
create a new user session or grant access to another account.

Example:
    python3 make_panda_natural_free_token.py --token 'eyJ...'
    python3 make_panda_natural_free_token.py --token 'eyJ...' --no-expiry

The no-expiry option uses 9999-12-31 23:59:59 UTC for compatibility with the
server's required numeric expiry.  It does not extend the underlying login
session: logging in again or clearing the session can still invalidate it.
"""

from __future__ import annotations

import argparse
import copy
import secrets
import sys
import time

import panda_jwt as jwt_encode


MODE = "force_natural_free_v1"
DEFAULT_DAYS = 30
MAX_DAYS = 90
# Latest whole second in year 9999; accepted by the existing server checks.
NO_EXPIRY_TIMESTAMP = 253402300799
TEST_APP_KEY = "SHYFBTESTMCH9057"


def issue_token(
    source_token: str, days: int = DEFAULT_DAYS, *, no_expiry: bool = False
) -> tuple[str, int]:
    """Copy a verified player session and add the narrowly-scoped test claim."""
    if not source_token:
        raise ValueError("--token is required")
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"--days must be between 1 and {MAX_DAYS}")

    payload = jwt_encode.jwt_decode(source_token, jwt_encode.PUBLIC_KEY)
    if not isinstance(payload, dict):
        raise ValueError("source token payload is invalid")
    if payload.get("app_key") != TEST_APP_KEY:
        raise ValueError("source token must belong to the supported Panda test merchant")
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ValueError("source token body is invalid")

    # Panda's normal session verification relies on these values.  Do not
    # synthesize or change them: this makes the issued token account-bound.
    required = ("account", "id", "login_time", "token")
    missing = [key for key in required if body.get(key) in (None, "")]
    if missing:
        raise ValueError(f"source token misses required session fields: {', '.join(missing)}")

    now = int(time.time())
    expires_at = NO_EXPIRY_TIMESTAMP if no_expiry else now + days * 24 * 60 * 60
    issued_payload = copy.deepcopy(payload)
    issued_body = copy.deepcopy(body)
    issued_body["panda_test"] = {
        "mode": MODE,
        "games": "all",
        "expires_at": expires_at,
        "token_id": secrets.token_urlsafe(12),
    }
    issued_payload["body"] = issued_body
    issued_payload["iat"] = now
    issued_payload["exp"] = expires_at

    # The local JWT signer matches the format used by Panda validation. The
    # inner ``body.token`` intentionally remains intact; it binds this launch
    # token to the source account's active cache session.
    return jwt_encode.jwt_encode(issued_payload, secret=jwt_encode.PUBLIC_KEY), expires_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, help="existing Panda player JWT")
    expiry = parser.add_mutually_exclusive_group()
    expiry.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"validity period (1-{MAX_DAYS}, default: {DEFAULT_DAYS})")
    expiry.add_argument(
        "--no-expiry", action="store_true",
        help="valid until year 9999; still requires the original active login session",
    )
    args = parser.parse_args()

    token, expires_at = issue_token(args.token, args.days, no_expiry=args.no_expiry)
    print(token)
    print(f"# expires_at={expires_at}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
