import uuid

from app.models.audit_event import AuditEvent
from app.models.membership import OrganizationMembership
from app.models.user import User


def _organization(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Audit Org {unique}", "slug": f"audit-org-{unique}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _member(db_session, organization_id, role):
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"Org {role}",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=uuid.UUID(organization_id),
            user_id=user.id,
            role=role,
            is_active=True,
            has_held_privileged_role=role in {"owner", "admin"},
            has_held_owner_role=role == "owner",
        )
    )
    db_session.commit()
    return user


def test_owners_read_the_audit_log_newest_first(client, db_session):
    organization_id = _organization(client)
    # In PostgreSQL these rows come from triggers; SQLite has none.
    for number, action in enumerate(["first.action", "second.action"], 1):
        db_session.add(
            AuditEvent(
                id=number,
                organization_id=uuid.UUID(organization_id),
                actor_database_login="eka_runtime",
                action=action,
                target_type="organization",
                target_id=uuid.UUID(organization_id),
                details={},
            )
        )
    db_session.commit()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/audit-events/"
    )

    assert response.status_code == 200
    assert [event["action"] for event in response.json()] == [
        "second.action",
        "first.action",
    ]


def test_members_and_viewers_cannot_read_the_audit_log(
    client,
    client_for_user,
    db_session,
):
    organization_id = _organization(client)

    for role in ("member", "viewer"):
        user = _member(db_session, organization_id, role)
        with client_for_user(user) as role_client:
            response = role_client.get(
                f"/api/v1/organizations/{organization_id}/audit-events/"
            )
        assert response.status_code == 403
