import uuid

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

from app.db.context import set_organization_context
from app.core.errors import InvalidInputError
from app.models import Document, FileUpload, FileUploadReader
from app.services.connection_service import create_connection, get_connection
from app.services.job_queue import enqueue_job
from app.services.object_storage import LocalObjectStorage
from app.services.sync_service import sync_connection
from app.services.upload_service import create_upload
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_as_worker = permissions._as_worker


@pytest.fixture
def world(perm_db):
    world = permissions.World(perm_db)
    _as_runtime(perm_db, world.owner)
    set_organization_context(perm_db, organization_id=world.organization)
    world.uploads = create_connection(
        perm_db,
        organization_id=world.organization,
        actor_user_id=world.owner,
        provider="file_upload",
        name="Uploads",
        settings={},
    ).id
    perm_db.flush()
    return world


def _upload_as(db, world, user_id, email, name, visibility, storage, readers=None):
    _as_runtime(db, user_id)
    connection = get_connection(
        db, organization_id=world.organization, connection_id=world.uploads
    )
    upload = create_upload(
        db,
        connection=connection,
        user_id=user_id,
        user_email=email,
        filename=name,
        data=f"contents of {name}".encode(),
        visibility=visibility,
        storage=storage,
        readers=readers,
    )
    db.flush()
    return upload.id


def test_a_member_uploads_and_visibility_decides_who_reads(
    perm_db, world, tmp_path
):
    db = perm_db
    storage = LocalObjectStorage(tmp_path)
    ana = f"ana@{world.domain}"
    _upload_as(db, world, world.ana, ana, "ana-private.txt", "private", storage)
    _upload_as(db, world, world.ana, ana, "handbook.txt", "organization", storage)

    _as_worker(db, world.organization)
    assert sync_connection(
        db, connection_id=world.uploads, storage=storage
    )["new_version"] == 2
    db.flush()

    def titles(user_id):
        _as_runtime(db, user_id)
        return sorted(db.scalars(select(Document.title)).all())

    assert titles(world.ana) == ["ana-private.txt", "handbook.txt"]
    assert titles(world.rui) == ["handbook.txt"]
    assert titles(world.owner) == ["handbook.txt"]


def test_upload_records_are_private_and_cannot_be_forged(
    perm_db, world, tmp_path
):
    db = perm_db
    storage = LocalObjectStorage(tmp_path)
    upload_id = _upload_as(
        db, world, world.ana, f"ana@{world.domain}", "salaries.txt",
        "private", storage,
    )

    # Rui, and even the owner, cannot see Ana's file names.
    for user in (world.rui, world.owner):
        _as_runtime(db, user)
        assert db.scalars(
            select(FileUpload.id).where(FileUpload.id == upload_id)
        ).all() == []

    # Rui cannot upload as Ana.
    _as_runtime(db, world.rui)
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(
                insert(FileUpload).values(
                    id=uuid.uuid4(),
                    organization_id=world.organization,
                    connection_id=world.uploads,
                    uploaded_by=world.rui,
                    uploader_email=f"ana@{world.domain}",
                    filename="fake.txt",
                    mime_type="text/plain",
                    size_bytes=1,
                    sha256="0" * 64,
                    original_object_key="x/original",
                    visibility="private",
                    status="active",
                )
            )
    assert "row-level security" in str(error.value.orig)


def test_members_queue_syncs_of_upload_connections_only(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)

    for connection_id, allowed in ((world.uploads, True), (world.connection, False)):
        def queue():
            enqueue_job(
                db,
                organization_id=world.organization,
                kind="connection.sync",
                created_by_user_id=world.ana,
                payload={"connection_id": str(connection_id)},
            )

        if allowed:
            queue()
        else:
            with pytest.raises(DBAPIError) as error:
                queue()
            assert "row-level security" in str(error.value.orig)


def test_people_shares_with_the_chosen_and_nobody_else(perm_db, world, tmp_path):
    db = perm_db
    storage = LocalObjectStorage(tmp_path)
    ana = f"ana@{world.domain}"
    _upload_as(db, world, world.ana, ana, "plan.txt", "people", storage, readers=[world.rui])

    _as_worker(db, world.organization)
    sync_connection(db, connection_id=world.uploads, storage=storage)
    db.flush()

    def titles(user_id):
        _as_runtime(db, user_id)
        return sorted(db.scalars(select(Document.title)).all())

    assert titles(world.ana) == ["plan.txt"]
    assert titles(world.rui) == ["plan.txt"]
    # Not chosen: the owner does not see it either.
    assert titles(world.owner) == []


def test_only_members_can_be_chosen_and_only_by_the_uploader(perm_db, world, tmp_path):
    db = perm_db
    storage = LocalObjectStorage(tmp_path)
    ana = f"ana@{world.domain}"

    with pytest.raises(InvalidInputError):
        with db.begin_nested():
            _upload_as(db, world, world.ana, ana, "x.txt", "people", storage, readers=[world.outsider])
    with pytest.raises(InvalidInputError):
        with db.begin_nested():
            _upload_as(db, world, world.ana, ana, "x.txt", "people", storage, readers=[])

    upload_id = _upload_as(db, world, world.ana, ana, "y.txt", "people", storage, readers=[world.rui])
    # Rui cannot add himself or anyone else to Ana's file.
    _as_runtime(db, world.rui)
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(
                text("SELECT app_private.add_upload_readers(:upload, :users)"),
                {"upload": upload_id, "users": [world.owner]},
            )
    assert "not an upload of the caller" in str(error.value.orig)
    # Nobody but the worker reads who was chosen.
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(select(FileUploadReader))


def test_the_list_says_the_kind_of_sharing_never_who(perm_db, world, tmp_path):
    db = perm_db
    storage = LocalObjectStorage(tmp_path)
    ana = f"ana@{world.domain}"
    _upload_as(db, world, world.ana, ana, "all.txt", "organization", storage)
    _upload_as(db, world, world.ana, ana, "mine.txt", "private", storage)
    _upload_as(db, world, world.ana, ana, "team.txt", "people", storage, readers=[world.rui])
    _as_worker(db, world.organization)
    sync_connection(db, connection_id=world.uploads, storage=storage)
    db.flush()

    def audiences(user_id):
        _as_runtime(db, user_id)
        rows = db.execute(
            text(
                "SELECT d.title, a.provider, a.audience"
                " FROM app_private.document_audiences(:organization) AS a"
                " JOIN documents AS d ON d.id = a.document_id"
            ),
            {"organization": world.organization},
        )
        return sorted(tuple(row) for row in rows)

    assert audiences(world.ana) == [
        ("all.txt", "file_upload", "organization"),
        ("mine.txt", "file_upload", "only_you"),
        ("team.txt", "file_upload", "people"),
    ]
    # Rui gets only what he can open, and no names.
    assert audiences(world.rui) == [
        ("all.txt", "file_upload", "organization"),
        ("team.txt", "file_upload", "people"),
    ]
