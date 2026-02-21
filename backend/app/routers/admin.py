from __future__ import annotations

# Admin APIs for user/channel/model/pricing management.
#
# This module is intentionally thin and delegates implementation to smaller
# modules to keep complexity low.

from fastapi import APIRouter

from ..services import upstream_models as upstream_models_service
from . import admin_billing, admin_pricing, admin_upstream, admin_users


router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(admin_users.router)
router.include_router(admin_upstream.router)
router.include_router(admin_pricing.router)
router.include_router(admin_billing.router)

# Backward-compatible alias for tests/tools that clear admin upstream cache.
_models_cache = upstream_models_service._models_cache
httpx = upstream_models_service.httpx
