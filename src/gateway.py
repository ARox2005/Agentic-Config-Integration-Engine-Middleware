import json
import os
from pathlib import Path

from pydantic import BaseModel
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

from .credential_resolver import resolve_credential

router = APIRouter()

# Path to the configs directory (middleware/configs/)
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def load_config(service_name: str, tenant_id: str = "default") -> dict:
    """
    Load a JSON config blueprint from the configs directory.
    Supports tenant-isolated configs: configs/{tenant_id}/{service}.json
    Falls back to flat configs/{service}.json for backward compatibility.
    """
    # Try tenant-isolated path first
    tenant_path = CONFIGS_DIR / tenant_id / f"{service_name}.json"
    if tenant_path.exists():
        with open(tenant_path, "r") as f:
            return json.load(f)

    # Fallback to flat path (backward compatibility)
    flat_path = CONFIGS_DIR / f"{service_name}.json"
    if flat_path.exists():
        with open(flat_path, "r") as f:
            return json.load(f)

    raise HTTPException(
        status_code=404,
        detail=f"No configuration found for service '{service_name}' "
               f"(tenant: '{tenant_id}'). "
               f"Checked: {tenant_path.name} and {flat_path.name}"
    )


def resolve_json_path(data: dict, path: str):
    """
    Simple JSONPath-like resolver.
    Handles paths like '$.applicant_data.firstName'
    and concatenation like "$.applicant_data.firstName + ' ' + $.applicant_data.lastName"
    """
    # Handle concatenation expressions (e.g., "$.x.y + ' ' + $.x.z")
    if "+" in path:
        parts = path.split("+")
        resolved_parts = []
        for part in parts:
            part = part.strip()
            if part.startswith("'") and part.endswith("'"):
                resolved_parts.append(part.strip("'"))
            elif part.startswith('"') and part.endswith('"'):
                resolved_parts.append(part.strip('"'))
            else:
                resolved_parts.append(str(resolve_json_path(data, part)))
        return "".join(resolved_parts)

    # Handle simple dot-notation paths: $.applicant_data.firstName
    if not path.startswith("$."):
        return path

    keys = path[2:].split(".")  # Strip '$.' and split
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise ValueError(f"Path '{path}' not found in payload. Failed at key '{key}'.")
    return current


def transform_request(incoming_payload: dict, mapping: dict) -> dict:
    """
    Apply the request_mapping rules from the config to transform
    the incoming payload into the format expected by the target API.
    """
    transformed = {}
    for target_field, source_path in mapping.items():
        try:
            transformed[target_field] = resolve_json_path(incoming_payload, source_path)
        except (ValueError, KeyError) as e:
            transformed[target_field] = None  # Graceful fallback
            print(f"[WARN] Transform failed for '{target_field}': {e}")
    return transformed


@router.post("/api/gateway/execute/{service_name}")
async def execute_gateway(service_name: str, request: Request, tenant_id: str = "default"):
    """
    Main gateway endpoint with tenant isolation.
    1. Loads the config for the requested service (tenant-aware)
    2. Transforms the incoming payload
    3. Resolves credentials
    4. Forwards to the target API
    5. Returns the response
    """
    # 1. Load config (tenant-aware)
    config = load_config(service_name, tenant_id)

    # 2. Parse incoming payload
    try:
        incoming_payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Transform the request
    mapping = config.get("schema_transformation_rules", {}).get("request_mapping", {})
    transformed_payload = transform_request(incoming_payload, mapping)

    # 4. Resolve credentials
    security = config.get("security_config", {})
    target_url = security.get("target_url")
    auth_type = security.get("auth_type", "Bearer")

    if not target_url:
        raise HTTPException(status_code=500, detail="No target_url in config")

    try:
        credential = resolve_credential(security.get("credential_vault_reference", ""))
    except (ValueError, EnvironmentError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 5. Forward the transformed request to the target API
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{auth_type} {credential}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(target_url, json=transformed_payload, headers=headers)
            target_data = response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach target service at {target_url}. Is the mock API running?"
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream call failed: {str(e)}")

    # 6. Return the response with metadata
    return {
        "service": service_name,
        "tenant_id": tenant_id,
        "target_system": config.get("integration_metadata", {}).get("target_system"),
        "api_version": config.get("integration_metadata", {}).get("api_version"),
        "upstream_status_code": response.status_code,
        "data": target_data,
    }

class SimulateRequest(BaseModel):
    """Accepts a config and payload inline for simulation."""
    config: dict          # The blueprint config (not yet deployed)
    payload: dict         # The test payload to transform and forward

@router.post("/api/gateway/simulate")
async def simulate_gateway(request: SimulateRequest):
    """
    Simulate an integration without deploying the config.
    Takes the config and payload inline, runs the full
    transform → resolve credentials → forward → return pipeline.
    """
    config = request.config
    incoming_payload = request.payload

    # 1. Transform the request
    mapping = config.get("schema_transformation_rules", {}).get("request_mapping", {})
    transformed_payload = transform_request(incoming_payload, mapping)

    # 2. Resolve credentials
    security = config.get("security_config", {})
    target_url = security.get("target_url")
    auth_type = security.get("auth_type", "Bearer")

    if not target_url:
        raise HTTPException(status_code=400, detail="No target_url in config")

    try:
        credential = resolve_credential(security.get("credential_vault_reference", ""))
    except (ValueError, EnvironmentError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Forward the transformed request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{auth_type} {credential}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(target_url, json=transformed_payload, headers=headers)
            target_data = response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach target service at {target_url}. Is the mock API running?"
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream call failed: {str(e)}")
        
    # 4. Return detailed simulation results
    return {
        "simulation": True,
        "target_system": config.get("integration_metadata", {}).get("target_system"),
        "steps": {
            "1_incoming_payload": incoming_payload,
            "2_transformation_rules": mapping,
            "3_transformed_payload": transformed_payload,
            "4_target_url": target_url,
            "5_auth_type": auth_type,
            "6_api_response": target_data,
            "7_upstream_status": response.status_code,
        },
    }

@router.post("/api/gateway/deploy/{service_name}")
async def deploy_remote_config(service_name: str, request: Request, tenant_id: str = "default"):
    """Receives a config blueprint over HTTP and saves it to the local configs folder."""
    try:
        config = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    # Sanitize service name
    safe_name = "".join(c for c in service_name.lower().replace(" ", "_") if c.isalnum() or c == "_")
    
    tenant_configs_dir = CONFIGS_DIR / tenant_id
    tenant_configs_dir.mkdir(parents=True, exist_ok=True)
    
    config_path = tenant_configs_dir / f"{safe_name}.json"
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    return {
        "status": "success", 
        "message": f"Config '{tenant_id}/{safe_name}.json' deployed successfully.", 
        "path": str(config_path)
    }

@router.delete("/api/gateway/configs")
async def reset_remote_configs(tenant_id: Optional[str] = None):
    """Deletes deployed config files remotely."""
    deleted = []
    
    if tenant_id:
        tenant_dir = CONFIGS_DIR / tenant_id
        if tenant_dir.exists():
            for config_file in tenant_dir.glob("*.json"):
                config_file.unlink()
                deleted.append(f"{tenant_id}/{config_file.name}")
    else:
        if CONFIGS_DIR.exists():
            for config_file in CONFIGS_DIR.glob("*.json"):
                config_file.unlink()
                deleted.append(config_file.name)
            for tenant_dir in CONFIGS_DIR.iterdir():
                if tenant_dir.is_dir():
                    for config_file in tenant_dir.glob("*.json"):
                        config_file.unlink()
                        deleted.append(f"{tenant_dir.name}/{config_file.name}")
                        
    return {"status": "configs_cleared", "deleted": deleted, "count": len(deleted)}