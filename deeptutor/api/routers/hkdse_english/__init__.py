"""English workbench routes, grouped by capability.

The application mounts this router at /api/v1/hkdse/english.
Implementation and request models live in paper, essay, integrated and oral.
"""

from fastapi import APIRouter

from . import essay, integrated, oral, paper

router = APIRouter()
router.include_router(paper.router)
router.include_router(essay.router)
router.include_router(integrated.router)
router.include_router(oral.router)
