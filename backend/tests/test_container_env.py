from scripts.container_env import container_environment, to_host_machine


def test_local_addresses_point_to_the_host_machine():
    assert (
        to_host_machine("postgresql+psycopg://user:pa%40ss@localhost:1996/eka_dev")
        == "postgresql+psycopg://user:pa%40ss@host.docker.internal:1996/eka_dev"
    )
    assert to_host_machine("http://127.0.0.1:11434/v1") == "http://host.docker.internal:11434/v1"
    assert to_host_machine("http://[::1]:11434/v1") == "http://host.docker.internal:11434/v1"


def test_other_addresses_and_settings_are_left_alone():
    assert to_host_machine("https://api.example.com/v1") == "https://api.example.com/v1"
    assert to_host_machine("postgresql://u:localhost@db.internal:5432/x") == (
        "postgresql://u:localhost@db.internal:5432/x"
    )
    file_values = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost:1996/eka_dev",
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "EKA_TEST_ADMIN_DATABASE_URL": "postgresql+psycopg://a:b@127.0.0.1:1999/eka_test",
        "LLM_MODEL": "localhost-model",
        "LLM_API_KEY": "",
    }
    given = {"EKA_TEST_ADMIN_DATABASE_URL": "postgresql+psycopg://a:b@host.docker.internal:1999/eka_test"}

    result = container_environment(file_values, given)

    assert result["DATABASE_URL"] == "postgresql+psycopg://u:p@host.docker.internal:1996/eka_dev"
    assert result["LLM_BASE_URL"] == "http://host.docker.internal:11434/v1"
    assert result["EKA_TEST_ADMIN_DATABASE_URL"] == given["EKA_TEST_ADMIN_DATABASE_URL"]
    assert "LLM_MODEL" not in result and "LLM_API_KEY" not in result
