import uuid

import pytest
from sqlalchemy import select

from app.core import credential_crypto as crypto
from app.core.config import settings
from app.models.credential import ConnectionCredential, OrganizationKey
from app.services.credential_service import load_credentials


SECRET = {"refresh_token": "very-secret-refresh-token-1234567890"}


@pytest.fixture
def master_key(monkeypatch):
    public, private = crypto.generate_key_pair()
    monkeypatch.setattr(
        settings, "CREDENTIALS_MASTER_PUBLIC_KEY", crypto.encode_key(public)
    )
    # The API process is configured with the public half only.
    monkeypatch.setattr(settings, "CREDENTIALS_MASTER_PRIVATE_KEY", None)
    return private


def _organization(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Secrets Org {unique}", "slug": f"secrets-{unique}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _connection(client, organization_id):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/connections/",
        json={"provider": "google_drive", "name": "Drive"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _url(organization_id, connection_id):
    return (
        f"/api/v1/organizations/{organization_id}/connections/"
        f"{connection_id}/credentials"
    )


# Sealing


def test_a_sealed_value_opens_only_with_its_key_and_context():
    public, private = crypto.generate_key_pair()
    other_public, other_private = crypto.generate_key_pair()
    sealed = crypto.seal(public, b"secret", context=b"here")

    assert crypto.open_sealed(private, sealed, context=b"here") == b"secret"
    assert b"secret" not in sealed

    with pytest.raises(crypto.CredentialCryptoError):
        crypto.open_sealed(private, sealed, context=b"elsewhere")
    with pytest.raises(crypto.CredentialCryptoError):
        crypto.open_sealed(other_private, sealed, context=b"here")

    tampered = bytearray(sealed)
    tampered[-1] ^= 1
    with pytest.raises(crypto.CredentialCryptoError):
        crypto.open_sealed(private, bytes(tampered), context=b"here")


def test_sealing_twice_gives_different_bytes():
    public, _ = crypto.generate_key_pair()

    assert crypto.seal(public, b"x", context=b"c") != crypto.seal(
        public, b"x", context=b"c"
    )


def test_keys_are_checked_when_decoded():
    public, _ = crypto.generate_key_pair()

    assert crypto.decode_key(crypto.encode_key(public)) == public
    with pytest.raises(ValueError):
        crypto.decode_key("too-short")
    assert crypto.fingerprint(public).startswith("x25519:")


# API


def test_admins_store_a_secret_the_api_never_returns(
    client, db_session, master_key
):
    organization_id = _organization(client)
    connection_id = _connection(client, organization_id)
    url = _url(organization_id, connection_id)

    assert client.get(url).json() == {
        "configured": False,
        "updated_at": None,
        "key": None,
    }

    response = client.put(url, json={"secret": SECRET})
    assert response.status_code == 204
    assert response.content == b""

    status = client.get(url).json()
    assert status["configured"] is True
    assert status["key"].startswith("x25519:")
    assert SECRET["refresh_token"] not in client.get(url).text

    # Stored sealed, not in clear.
    db_session.expire_all()
    stored = db_session.scalars(select(ConnectionCredential)).one()
    assert SECRET["refresh_token"].encode() not in stored.sealed


def test_only_the_master_private_key_opens_it(client, db_session, master_key):
    organization_id = _organization(client)
    connection_id = _connection(client, organization_id)
    client.put(_url(organization_id, connection_id), json={"secret": SECRET})

    ids = dict(
        organization_id=uuid.UUID(organization_id),
        connection_id=uuid.UUID(connection_id),
    )

    # Without the private key (the API's configuration) nothing opens.
    with pytest.raises(Exception) as error:
        load_credentials(db_session, **ids)
    assert error.value.status_code == 503

    _, wrong_private = crypto.generate_key_pair()
    with pytest.raises(crypto.CredentialCryptoError):
        load_credentials(db_session, master_private=wrong_private, **ids)

    assert load_credentials(db_session, master_private=master_key, **ids) == (
        SECRET
    )


def test_a_secret_moved_to_another_connection_does_not_open(
    client, db_session, master_key
):
    organization_id = _organization(client)
    first = _connection(client, organization_id)
    second = client.post(
        f"/api/v1/organizations/{organization_id}/connections/",
        json={
            "provider": "postgresql",
            "name": "Warehouse",
            "settings": {"host": "db.example.com", "database": "warehouse"},
        },
    ).json()["id"]
    client.put(_url(organization_id, first), json={"secret": SECRET})
    client.put(_url(organization_id, second), json={"secret": {"x": "y"}})

    db_session.expire_all()
    rows = {
        str(row.connection_id): row
        for row in db_session.scalars(select(ConnectionCredential))
    }
    rows[second].sealed = rows[first].sealed
    db_session.commit()

    with pytest.raises(crypto.CredentialCryptoError):
        load_credentials(
            db_session,
            organization_id=uuid.UUID(organization_id),
            connection_id=uuid.UUID(second),
            master_private=master_key,
        )


def test_replacing_a_secret_keeps_one_organization_key(
    client, db_session, master_key
):
    organization_id = _organization(client)
    connection_id = _connection(client, organization_id)
    url = _url(organization_id, connection_id)

    client.put(url, json={"secret": SECRET})
    client.put(url, json={"secret": {"refresh_token": "new"}})

    db_session.expire_all()
    assert len(db_session.scalars(select(OrganizationKey)).all()) == 1
    assert len(db_session.scalars(select(ConnectionCredential)).all()) == 1
    assert load_credentials(
        db_session,
        organization_id=uuid.UUID(organization_id),
        connection_id=uuid.UUID(connection_id),
        master_private=master_key,
    ) == {"refresh_token": "new"}


def test_secrets_are_refused_when_storage_is_not_configured(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "CREDENTIALS_MASTER_PUBLIC_KEY", None)
    organization_id = _organization(client)
    connection_id = _connection(client, organization_id)

    response = client.put(
        _url(organization_id, connection_id), json={"secret": SECRET}
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_empty_secrets_and_disconnected_sources_are_refused(
    client, master_key
):
    organization_id = _organization(client)
    connection_id = _connection(client, organization_id)
    url = _url(organization_id, connection_id)

    assert client.put(url, json={"secret": {}}).status_code == 422

    client.post(
        f"/api/v1/organizations/{organization_id}/connections/"
        f"{connection_id}/disconnect"
    )
    assert client.put(url, json={"secret": SECRET}).status_code == 409


def test_a_secret_never_appears_in_a_repr():
    from app.schemas.credential import CredentialsUpdate

    data = CredentialsUpdate(secret=SECRET)

    assert SECRET["refresh_token"] not in repr(data)
    assert SECRET["refresh_token"] not in str(data)
