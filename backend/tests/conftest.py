import importlib
import os
import sys
from pathlib import Path

# ── Path isolation ──
# Ensure this project's `app` package takes priority over the AI_Governance_Hub
# editable install which also registers an `app` namespace via sys.meta_path.
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Patch the editable finder's MAPPING to remove the conflicting `app` entry.
try:
    _editable_finder = importlib.import_module(
        "__editable___ai_governance_backend_0_1_0_finder"
    )
    _editable_finder.MAPPING.pop("app", None)
except ImportError:
    pass  # Finder not present in this environment — no action needed.

# Clear any stale `app` module cache so re-import uses the correct path.
for _key in list(sys.modules.keys()):
    if _key == "app" or _key.startswith("app."):
        del sys.modules[_key]

# ── Required environment variables for Settings ──
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres_dev@localhost:5433/expense_tracker",
)
os.environ.setdefault(
    "SYNC_DATABASE_URL",
    "postgresql://postgres:postgres_dev@localhost:5433/expense_tracker",
)

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def rsa_keys(tmp_path, monkeypatch):
    """Generate ephemeral RSA keys and patch settings to use them."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path = tmp_path / "jwt_private.pem"
    pub_path = tmp_path / "jwt_public.pem"
    priv_path.write_bytes(private_pem)
    pub_path.write_bytes(public_pem)

    monkeypatch.setattr("app.core.config.settings.JWT_PRIVATE_KEY_PATH", str(priv_path))
    monkeypatch.setattr("app.core.config.settings.JWT_PUBLIC_KEY_PATH", str(pub_path))
    return str(priv_path), str(pub_path)
