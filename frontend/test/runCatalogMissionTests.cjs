/**
 * Create the isolated multi-module catalog fixture and run the real mission
 * through VS Code Insiders + NL Coder development extension.
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'catalog-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'catalog-mission-test.log');

function codeInsidersPath() {
    return process.env.VSCODE_INSIDERS_EXE ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

const FILES = {
    'catalog/__init__.py': '',
    'catalog/models.py': `from __future__ import annotations

from dataclasses import dataclass


class InsufficientStock(Exception):
    """Raised when a reservation exceeds currently available stock."""


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    stock: int


@dataclass(frozen=True)
class Reservation:
    id: str
    product_id: str
    quantity: int
    created_at: float
    expires_at: float
`,
    'catalog/repository.py': `from __future__ import annotations

from catalog.models import Product


class CatalogRepository:
    """Existing product storage; the new reservation modules depend on it."""

    def __init__(self):
        self._products: dict[str, Product] = {}

    def add_product(self, product: Product) -> Product:
        self._products[product.id] = product
        return product

    def get_product(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def list_products(self) -> list[Product]:
        return list(self._products.values())
`,
    'catalog/service.py': `from __future__ import annotations

from catalog.models import Product
from catalog.repository import CatalogRepository


class CatalogService:
    def __init__(self, repository: CatalogRepository):
        self.repository = repository

    def create_product(self, product_id: str, name: str, stock: int) -> Product:
        if stock < 0:
            raise ValueError("stock must be non-negative")
        return self.repository.add_product(Product(product_id, name, stock))

    def get_product(self, product_id: str) -> Product:
        product = self.repository.get_product(product_id)
        if product is None:
            raise KeyError(product_id)
        return product

    def list_products(self) -> list[Product]:
        return self.repository.list_products()
`,
    'catalog/api.py': `from __future__ import annotations

from catalog.repository import CatalogRepository
from catalog.service import CatalogService


def bootstrap_catalog() -> CatalogService:
    repository = CatalogRepository()
    service = CatalogService(repository)
    service.create_product("p1", "Widget", 5)
    service.create_product("p2", "Gadget", 2)
    return service
`,
    'tests/test_catalog_existing.py': `from catalog.api import bootstrap_catalog


def test_existing_product_api_is_preserved():
    service = bootstrap_catalog()
    assert service.get_product("p1").stock == 5
    assert [product.id for product in service.list_products()] == ["p1", "p2"]
`,
    'tests/test_reservations.py': `import pytest

from catalog import reservation_api as api
from catalog.models import InsufficientStock, Product, Reservation
from catalog.repository import CatalogRepository
from catalog.reservation_repository import ReservationRepository
from catalog.reservation_service import ReservationService


def make_service():
    catalog = CatalogRepository()
    catalog.add_product(Product("p1", "Widget", 5))
    catalog.add_product(Product("p2", "Gadget", 2))
    return ReservationService(catalog, ReservationRepository())


def test_reservation_reduces_available_stock():
    service = make_service()
    reservation = service.reserve("p1", 2, now=100.0, ttl=30.0)
    assert isinstance(reservation, Reservation)
    assert reservation.quantity == 2
    assert reservation.expires_at == 130.0
    assert service.available("p1", now=100.0) == 3


def test_insufficient_stock_is_rejected():
    service = make_service()
    with pytest.raises(InsufficientStock):
        service.reserve("p2", 3, now=100.0)


def test_release_restores_stock_and_reports_unknown_id():
    service = make_service()
    reservation = service.reserve("p1", 2, now=100.0)
    assert service.release(reservation.id) is True
    assert service.available("p1", now=100.0) == 5
    assert service.release("missing-reservation") is False


def test_expired_reservation_no_longer_blocks_stock():
    service = make_service()
    service.reserve("p1", 1, now=100.0, ttl=10.0)
    service.reserve("p1", 2, now=105.0, ttl=20.0)
    assert service.available("p1", now=105.0) == 2
    assert service.expire(now=111.0) == 1
    assert service.available("p1", now=111.0) == 3
    assert service.expire(now=130.0) == 1
    assert service.available("p1", now=130.0) == 5


def test_api_helpers_share_service():
    service = make_service()
    reservation = api.api_reserve(service, "p1", 1, now=200.0, ttl=10.0)
    assert api.api_available(service, "p1", now=200.0) == 4
    assert api.api_release(service, reservation.id) is True
    assert api.api_available(service, "p1", now=200.0) == 5
`,
    'README.md': '# Isolated catalog fixture for NL Code acceptance\n'
};

function prepare() {
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot,
        path.join(projectDir, 'catalog'), path.join(projectDir, 'tests')]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    for (const [relative, content] of Object.entries(FILES)) {
        const target = path.join(projectDir, relative);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, content, 'utf8');
    }
    const userSettings = path.join(userDataDir, 'User');
    fs.mkdirSync(userSettings, { recursive: true });
    fs.writeFileSync(path.join(userSettings, 'settings.json'), JSON.stringify({
        'nlCodingAgent.allowExecution': true,
        'nlCodingAgent.engineRoot': repoRoot,
        'nlCodingAgent.requestTimeoutSeconds': 900
    }, null, 2));
}

function main() {
    const executable = codeInsidersPath();
    if (!fs.existsSync(executable)) {
        console.error('VS Code Insiders not found at ' + executable);
        process.exit(2);
    }
    prepare();
    const args = [
        '--extensionDevelopmentPath=' + frontendDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'catalogMission.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-extensions',
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    const env = {
        ...process.env,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.ELECTRON_NO_ATTACH_CONSOLE;
    console.log('launching: "' + executable + '" ' + args.join(' '));
    console.log('catalog mission log: ' + logPath);
    const child = spawn(executable, args, { cwd: repoRoot, env, windowsHide: false });
    let output = '';
    const sink = (chunk) => { const text = chunk.toString(); output += text; process.stdout.write(text); };
    child.stdout.on('data', sink);
    child.stderr.on('data', sink);
    const timeout = setTimeout(() => {
        console.error('catalog mission timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 1200000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        if (code === 0 && output.includes('CATALOG-MISSION-ACCEPTANCE-PASS')) {
            console.log('== CATALOG-MISSION-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== CATALOG-MISSION-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
