"""
Utilities for encoding, decoding, and validating JWT tokens.
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from jwt import decode, encode
from jwt import exceptions as jwt_exceptions
from quart import redirect, url_for


class JWTError(Exception):
    """Base Class for JWT errors"""


class JWTAppIdMissingError(JWTError):
    """Raised when the app_id is missing in JWT header."""


class JWTPublicKeyNotFoundError(JWTError):
    """Raised when the public key for a given app_id is not found."""


class JWTPrivateKeyNotFoundError(JWTError):
    """Raised when the private key is not found."""


class BlacklistedTokenError(JWTError):
    """Raised when the provided token is blacklisted."""


class InvalidTokenError(JWTError):
    """Raised when the provided token is invalid."""


class InvalidClientTokenError(JWTError):
    """Raised when the provided client token is invalid."""


class InvalidEmailTokenError(JWTError):
    """Raised when the provided email token is invalid."""


class JWTExpired(JWTError):
    """Raised when the provided token is expired."""


def decode_client_jwt_token(jwt_token, keys_directory: Path):
    """
    Decode the JWT token using the correct public key based on app_id.
    """
    if not jwt_token:
        raise JWTError("No JWT token provided in query parameters.")
    try:
        app_id_field = os.getenv("MEMBRANE_APP_ID_FIELD")
        redirect_url_field = os.getenv("MEMBRANE_REDIRECT_URL_FIELD")
        algorithm = os.getenv("MEMBRANE_ENCODE_ALGORITHM")

        # Temporarily decode the token to fetch the app_id
        unverified_decoded_token = decode(
            jwt_token, options={"verify_signature": False}
        )
        if app_id_field not in unverified_decoded_token:
            raise JWTAppIdMissingError("No app id in JWT payload.")

        app_id = unverified_decoded_token[app_id_field]

        # Look for a corresponding public key file
        public_key_path = keys_directory / f"{app_id}_public_key.pem"

        if not public_key_path.exists():
            raise JWTPublicKeyNotFoundError(
                f"Public key not found for app_id: {app_id} {unverified_decoded_token}."
            )

        with public_key_path.open("r") as key_file:
            public_key = key_file.read()

        # Decode the token using the fetched public key
        decoded_token = decode(jwt_token, public_key, algorithms=[algorithm])
        # Retrieve the redirect URL.
        redirect_url = decoded_token[redirect_url_field]
        if not redirect_url:
            raise JWTError("No redirect URL found in Token.")

        expired_time = decoded_token[os.getenv("MEMBRANE_EXPIRATION_FIELD")]

        # Get current time
        current_time = datetime.utcnow()
        current_timestamp = int(current_time.timestamp())

        # Check for token expiration
        if current_timestamp > expired_time:
            raise JWTExpired("JWT token has expired.")

        return decoded_token

    except (jwt_exceptions.InvalidTokenError, jwt_exceptions.DecodeError) as error:
        raise JWTError(str(error)) from error


def login_redirect_with_client_jwt(
    clientapp_token, client_public_keys_directory, membrane_frontend
):
    """
    Validates the client application token and redirects to the Membrane Frontend.

    Args:
        clientapp_token (str): The JWT token provided by the client application.
        client_public_keys_directory (Path): Path to the directory containing client
        public keys.
        membrane_frontend (str): The URL for redirecting to the membrane Frontend.

    Returns:
        Response: A redirection response to the Membrane Frontend with the token as
        a parameter.

    Raises:
        InvalidClientTokenError: If the token validation or decoding fails.
    """
    try:
        decode_client_jwt_token(clientapp_token, client_public_keys_directory)
        redirect_url_with_token = f"{membrane_frontend}?token={clientapp_token}"
        return redirect(redirect_url_with_token)
    except Exception as error:
        logging.error("Failed to decode client application token: %s", error)
        raise InvalidClientTokenError(
            "Failed to decode client application token."
        ) from error


def process_email_verification_token(email_token, server_public_key, token_blacklist):
    """
    Processes a token from an email verification URL.

    The function decodes the given email token, validates its authenticity, and adds it
    to a blacklist to prevent reuse. Upon successful validation, a redirection is
    performed based on the decoded token's information.

    Args:
        email_token (str): The JWT token from the email verification URL.
        server_public_key (Path): Path to the public key used for JWT decoding.
        token_blacklist (set): A set to store tokens that should not be reused.

    Returns:
        Response: A redirection response based on the decoded token's information.

    Raises:
        JWTError: If there's an issue with the token's validation or decoding.
    """
    try:
        # Decode the email token
        decoded_email_token = decode_email_verification_token(
            email_token, server_public_key, token_blacklist
        )

        # Add the token to the blacklist to ensure it's not reused
        token_blacklist.add(email_token)

        # Construct the redirect URL using the decoded information and redirect
        redirect_url_field = os.getenv("MEMBRANE_REDIRECT_URL_FIELD")
        email_token_redirect = (
            f"{decoded_email_token[redirect_url_field]}?token={email_token}"
        )
        return redirect(email_token_redirect, code=302)

    except JWTError as error:
        # Handle JWT specific errors (like expired or invalid tokens)
        logging.error(f"Failed to verify and decode email token: {error}")
        raise


def decode_email_verification_token(jwt_token, server_public_key_path, token_blacklist):
    """
    Decodes and validates an email verification JWT token.

    Args:
        jwt_token (str): The JWT token to decode.
        server_public_key_path (Path): Path to the server's public key for token
        decoding.
        token_blacklist (set): A set of blacklisted tokens.

    Returns:
        dict: Decoded JWT payload.

    Raises:
        JWTError: For various JWT-related issues.
    """
    if not jwt_token:
        raise JWTError("No JWT token provided in query parameters.")

    # Check blacklist.
    if jwt_token in token_blacklist:
        raise BlacklistedTokenError("This token has been blacklisted.")

    # Fetch public key.
    with server_public_key_path.open("r") as key_file:
        public_key = key_file.read()

    try:
        algorithm = os.getenv("MEMBRANE_ENCODE_ALGORITHM")
        redirect_url_field = os.getenv("MEMBRANE_REDIRECT_URL_FIELD")
        # Decode the token using the provided public key.
        decoded_token = decode(jwt_token, public_key, algorithms=[algorithm])

        # Check redirect URL existence.
        if redirect_url_field not in decoded_token:
            raise JWTError("No redirect URL found in token.")

        # Check token expiration.
        expired_time = decoded_token[os.getenv("MEMBRANE_EXPIRATION_FIELD")]
        current_time = datetime.utcnow()
        if current_time.timestamp() > expired_time:
            raise JWTExpired("JWT token has expired.")

        return decoded_token

    except jwt_exceptions.InvalidTokenError as error:
        raise InvalidTokenError(str(error)) from error


def generate_email_verification_token(
    email, redirect_url, expiration_seconds, server_private_key_path
):
    """
    Generate an email verification token and the corresponding verification URL.
    """
    # Generate token expiration timestamp.
    redirect_url_field = os.getenv("MEMBRANE_REDIRECT_URL_FIELD")
    expiration_field = os.getenv("MEMBRANE_EXPIRATION_FIELD")
    expiration_time = datetime.utcnow() + timedelta(seconds=expiration_seconds)
    expiration_timestamp = int(expiration_time.timestamp())

    # Token payload.
    payload = {
        "sub": email,
        redirect_url_field: redirect_url,
        expiration_field: expiration_timestamp,
    }

    # Encode email token using the server's dedicated private key.
    email_token = encode_email_verification_token(payload, server_private_key_path)

    # Construct the verification URL which includes the new JWT token.
    verification_url = url_for("authenticate", token=email_token, _external=True)

    return verification_url


def encode_email_verification_token(payload, server_private_key_path):
    """
    Encodes the given payload into a JWT using the RS256 algorithm.

    Args:
        payload (dict): The payload to encode.
        server_private_key_path (Path): Path to the server's private key.

    Returns:
        str: Encoded JWT token.

    Raises:
        JWTPrivateKeyNotFoundError: If the private key file doesn't exist.
        JWTError: For other JWT-related issues.
    """
    if not server_private_key_path.exists():
        raise JWTPrivateKeyNotFoundError("Private key not found")

    with server_private_key_path.open("r") as key_file:
        private_key = key_file.read()

    try:
        algorithm = os.getenv("MEMBRANE_ENCODE_ALGORITHM")
        jwt_token = encode(payload, private_key, algorithm=algorithm)
        return jwt_token
    except Exception as error:
        raise JWTError(f"Failed to encode JWT token. Error: {error}") from error


def redirect_to_client_app_using_verification_token(
    verification_token, server_public_key, token_blacklist
):
    """
    Decodes the email verification token and redirects to the appropriate endpoint.

    Args:
        clientapp_token (str): The JWT token from the client application.
        server_public_key (Path): Path to the public key used for JWT decoding.
        token_blacklist (set): A set to store tokens that should not be reused.

    Returns:
        Response: A redirection response based on the decoded token's information.

    Raises:
        InvalidEmailTokenError: If there's an issue with the token's validation or
        decoding.
    """
    try:
        # Attempt to decode the client application's email token
        return process_email_verification_token(
            verification_token, server_public_key, token_blacklist
        )
    except BlacklistedTokenError:
        logging.exception("Token is blacklisted, trying without blacklist...")
    except InvalidTokenError:
        logging.error("Invalid token provided.")
        raise

    # If blacklisted or any other error, handle the token without using the blacklist.
    # This is return user to client application to restart SSO.
    try:
        redirect_url_field = os.getenv("MEMBRANE_REDIRECT_URL_FIELD")
        verification_decoded_token = decode_email_verification_token(
            verification_token, server_public_key, {}
        )
        return redirect(verification_decoded_token[redirect_url_field])
    except (InvalidTokenError, BlacklistedTokenError) as error:
        raise InvalidEmailTokenError(
            "Failed to decode client application token."
        ) from error
