from contextlib import contextmanager

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.authentication import get_current_user
from app.db.base import Base
from app.db.context import set_identity_context
from app.db.session import get_db
from app.main import app
from app.models import User


# Create an in-memory SQLite database for testing.
TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture
def db_session():
    # Create all database tables before each test.
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def authenticated_user(db_session):
    user = User(
        email="authenticated@example.com",
        full_name="Authenticated Test User",
        is_active=True,
    )

    db_session.add(user)
    db_session.flush()

    return user


@pytest.fixture
def client(db_session, authenticated_user):
    # Override the application's database dependency.
    def override_get_db():
        yield db_session

    # Simulate successful authentication, including identity context.
    def override_get_current_user():
        set_identity_context(
            db_session,
            issuer="https://test-identity.example.com/",
            subject=f"test-subject-{authenticated_user.id}",
            user_id=authenticated_user.id,
        )
        return authenticated_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(db_session):
    # Override only the database dependency.
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def client_for_user(db_session):
    @contextmanager
    def create_client(user):
        previous_get_db = app.dependency_overrides.get(get_db)
        previous_get_current_user = app.dependency_overrides.get(
            get_current_user
        )

        def override_get_db():
            yield db_session

        # Simulate the same identity-context setup as real authentication.
        def override_get_current_user():
            set_identity_context(
                db_session,
                issuer="https://test-identity.example.com/",
                subject=f"test-subject-{user.id}",
                user_id=user.id,
            )
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = (
            override_get_current_user
        )

        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            if previous_get_db is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_get_db

            if previous_get_current_user is None:
                app.dependency_overrides.pop(
                    get_current_user,
                    None,
                )
            else:
                app.dependency_overrides[get_current_user] = (
                    previous_get_current_user
                )

    return create_client
