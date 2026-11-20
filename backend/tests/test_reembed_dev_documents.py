from scripts.reembed_dev_documents import check_target


def test_only_the_development_database_is_accepted():
    assert check_target("postgresql+psycopg://admin:x@host.docker.internal:1996/eka_dev") is None
    assert "port 1996" in check_target("postgresql+psycopg://admin:x@db.example:5432/prod")
    assert "not set" in check_target(None)
