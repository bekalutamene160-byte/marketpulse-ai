import pytest
from pydantic import ValidationError

from marketpulse.config import Settings

NEON_LIKE = "postgresql://app_user:s3cretpw@ep-demo-pooler.region.aws.neon.tech/db?sslmode=require"


def make(**overrides: object) -> Settings:
    # _env_file=None: ignore any local .env so tests are deterministic.
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults_are_safe_for_local_development() -> None:
    s = make(database_url=None, redis_url=None)
    assert s.environment == "local"
    assert s.database_url is None
    assert s.redis_url is None
    assert s.probe_timeout_seconds == 10.0


def test_config_holds_no_business_data() -> None:
    # Principle 11 / 4.1: markets, currencies, categories and retailer names are tenant data.
    fields = set(Settings.model_fields)
    assert not fields & {"retailer_name", "currency", "market_country", "product_category"}


def test_blank_url_means_unset() -> None:
    s = make(database_url="", redis_url="   ")
    assert s.database_url is None
    assert s.redis_url is None


def test_log_level_is_case_insensitive() -> None:
    assert make(log_level="debug").log_level == "DEBUG"


def test_environment_variable_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_LOG_LEVEL", "error")
    assert make().log_level == "ERROR"


def test_database_url_must_be_postgres() -> None:
    with pytest.raises(ValidationError):
        make(database_url="mysql://u:p@h/db")


def test_redis_url_must_be_redis() -> None:
    with pytest.raises(ValidationError):
        make(redis_url="http://example.com")


def test_validation_error_never_echoes_the_secret() -> None:
    with pytest.raises(ValidationError) as excinfo:
        make(database_url="mysql://user:topsecretpw@host/db")
    assert "topsecretpw" not in str(excinfo.value)


def test_secret_is_hidden_in_repr() -> None:
    s = make(database_url=NEON_LIKE)
    assert "s3cretpw" not in repr(s)
    assert "s3cretpw" not in str(s)


def test_dsn_drops_sqlalchemy_driver_suffix() -> None:
    s = make(database_url="postgresql+psycopg://u:p@h/db")
    assert s.database_dsn == "postgresql://u:p@h/db"


@pytest.mark.parametrize("bad", [0, -1, 61])
def test_probe_timeout_bounds(bad: float) -> None:
    with pytest.raises(ValidationError):
        make(probe_timeout_seconds=bad)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_local_requires_database(env: str) -> None:
    with pytest.raises(ValidationError):
        make(environment=env, database_url=None)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_local_requires_tls_database(env: str) -> None:
    with pytest.raises(ValidationError):
        make(environment=env, database_url="postgresql://u:p@h/db")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_local_rejects_wildcard_cors(env: str) -> None:
    with pytest.raises(ValidationError):
        make(environment=env, database_url=NEON_LIKE, cors_origins=["*"])


def test_production_requires_tls_redis() -> None:
    with pytest.raises(ValidationError):
        make(environment="production", database_url=NEON_LIKE, redis_url=None)
    with pytest.raises(ValidationError):
        make(environment="production", database_url=NEON_LIKE, redis_url="redis://h:6379")


def test_production_accepts_a_complete_secure_configuration() -> None:
    s = make(environment="production", database_url=NEON_LIKE, redis_url="rediss://:p@h:6379")
    assert s.environment == "production"


# --- Phase 1 settings ---
def test_database_direct_url_blank_means_unset() -> None:
    assert make(database_direct_url="").database_direct_url is None


def test_database_direct_url_must_be_postgres() -> None:
    with pytest.raises(ValidationError):
        make(database_direct_url="mysql://u:p@h/db")


def test_database_direct_dsn_strips_driver_suffix() -> None:
    s = make(database_direct_url="postgresql+psycopg://u:p@h/db")
    assert s.database_direct_dsn == "postgresql://u:p@h/db"


def test_db_app_role_defaults_to_marketpulse_app() -> None:
    assert make().db_app_role == "marketpulse_app"


def test_db_app_role_rejects_unsafe_names() -> None:
    # Hyphens, spaces and SQL metacharacters are rejected: the role name is
    # interpolated into DDL/GRANTs.
    for bad in ("marketpulse-app", "bad role", "role; DROP", "1starts-with-digit"):
        with pytest.raises(ValidationError):
            make(db_app_role=bad)


def test_db_app_role_accepts_underscore_identifiers() -> None:
    assert make(db_app_role="marketpulse_app").db_app_role == "marketpulse_app"
    assert make(db_app_role="app_role_v2").db_app_role == "app_role_v2"


def test_dev_tenant_header_defaults_off() -> None:
    assert make().enable_dev_tenant_header is False


@pytest.mark.parametrize("env", ["staging", "production"])
def test_dev_tenant_header_is_forbidden_in_non_local(env: str) -> None:
    with pytest.raises(ValidationError):
        make(environment=env, database_url=NEON_LIKE, enable_dev_tenant_header=True)


def test_pool_settings_are_bounded() -> None:
    with pytest.raises(ValidationError):
        make(db_pool_size=0)
    with pytest.raises(ValidationError):
        make(db_max_overflow=21)


# --- Phase 2: auth settings ---
def test_auth_session_and_rate_limit_defaults() -> None:
    s = make(database_url=None, redis_url=None)
    assert s.session_lifetime_hours == 168
    assert s.auth_rate_limit_attempts == 10
    assert s.auth_rate_limit_window_seconds == 300


def test_auth_settings_are_bounded() -> None:
    with pytest.raises(ValidationError):
        make(session_lifetime_hours=0)
    with pytest.raises(ValidationError):
        make(session_lifetime_hours=721)
    with pytest.raises(ValidationError):
        make(auth_rate_limit_attempts=0)
    with pytest.raises(ValidationError):
        make(auth_rate_limit_window_seconds=5)
