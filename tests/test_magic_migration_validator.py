from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _validator():
    path = (
        Path(__file__).parents[1]
        / "skills"
        / "add-mom-magic-api"
        / "scripts"
        / "validate_magic_migration.py"
    )
    spec = importlib.util.spec_from_file_location("validate_magic_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID_MIGRATION = r'''
DELETE FROM magic_api_file
WHERE file_path = '/magic-api/api/MES接口/PDA汽车铸棒库存.ms';

INSERT INTO magic_api_file (file_path, file_content) VALUES (
    '/magic-api/api/MES接口/PDA汽车铸棒库存.ms',
    $magic${
  "id": "d993c6f0c97b4a14964106b8b28c4d25",
  "groupId": "f5916dd2b2654c339457346ab6465cd8",
  "name": "PDA汽车铸棒库存",
  "path": "/pda/autoCastRodInventory/overview",
  "method": "POST",
  "parameters": [],
  "requestBody": "{\"locationIds\": [], \"alloy\": \"\"}"
}
================================
import ifc;
var tenantId = ifc.getTenantId();
var rows = db.camel().select("""
SELECT inventory.id::varchar AS inventory_id
FROM mes_auto_cast_rod_inventory inventory
WHERE inventory.tenant_id = #{tenantId}
""", {tenantId: tenantId});
return rows;
$magic$
);

DELETE FROM def_resource_api
WHERE uri = '/magic/api/mes/pda/autoCastRodInventory/overview'
  AND request_method = 'POST';

DELETE FROM def_resource
WHERE code = 'mes:pda:foundryBar:autoCastRodInventory';

INSERT INTO def_resource(code, path)
SELECT 'mes:pda:foundryBar:autoCastRodInventory',
       '/pages/foundryBar/autoCastRodInventory/index'
FROM def_resource parent
WHERE parent.code = 'mes:pda:callStick';

INSERT INTO def_resource_api(
    resource_id, controller, spring_application_name, request_method, uri
)
SELECT menu.id, 'MagicController', 'lamp-system-server', 'POST',
       '/magic/api/mes/pda/autoCastRodInventory/overview'
FROM def_resource menu
WHERE menu.code = 'mes:pda:foundryBar:autoCastRodInventory';

INSERT INTO def_tenant_resource_rel(tenant_id, resource_id)
SELECT 1, menu.id
FROM def_resource menu
WHERE menu.code = 'mes:pda:foundryBar:autoCastRodInventory'
  AND NOT EXISTS (
      SELECT 1 FROM def_tenant_resource_rel relation
      WHERE relation.tenant_id = 1 AND relation.resource_id = menu.id
  );
'''


def test_validator_accepts_consistent_magic_menu_permission_contract() -> None:
    diagnostics = _validator().validate_text(
        VALID_MIGRATION,
        expected_group_id="f5916dd2b2654c339457346ab6465cd8",
        expected_group_path="/mes",
        expected_menu_route="/pages/foundryBar/autoCastRodInventory/index",
    )

    assert diagnostics == []


@pytest.mark.parametrize(
    ("migration", "code"),
    [
        (
            VALID_MIGRATION.replace(
                '"groupId": "f5916dd2b2654c339457346ab6465cd8"',
                '"groupId": "wrong-group"',
            ),
            "MAGIC_GROUP_MISMATCH",
        ),
        (
            VALID_MIGRATION.replace(
                '"parameters": []',
                '"parameters": [{"name": "tenantId"}]',
            ),
            "MAGIC_TENANT_PARAMETER_EXPOSED",
        ),
        (
            VALID_MIGRATION.replace(
                "/magic/api/mes/pda/autoCastRodInventory/overview",
                "/magic/api/wrong/pda/autoCastRodInventory/overview",
            ),
            "PERMISSION_URI_MISMATCH",
        ),
        (
            VALID_MIGRATION.replace("INSERT INTO def_tenant_resource_rel", "-- removed"),
            "TENANT_GRANT_MISSING",
        ),
        (
            VALID_MIGRATION.replace(
                "inventory.id::varchar AS inventory_id",
                "inventory.id AS inventory_id",
            ),
            "SNOWFLAKE_ID_NOT_STRING",
        ),
        (
            VALID_MIGRATION.replace(
                "/pages/foundryBar/autoCastRodInventory/index",
                "/pages/wrong/index",
            ),
            "MENU_ROUTE_MISMATCH",
        ),
        (
            VALID_MIGRATION.replace('  "id":', '  "id"'),
            "MAGIC_JSON_INVALID",
        ),
        (
            VALID_MIGRATION.replace(
                "================================",
                "================",
            ),
            "MAGIC_DELIMITER_MISSING",
        ),
    ],
)
def test_validator_reports_stable_contract_diagnostics(
    migration: str,
    code: str,
) -> None:
    diagnostics = _validator().validate_text(
        migration,
        expected_group_id="f5916dd2b2654c339457346ab6465cd8",
        expected_group_path="/mes",
        expected_menu_route="/pages/foundryBar/autoCastRodInventory/index",
    )

    assert code in diagnostics
