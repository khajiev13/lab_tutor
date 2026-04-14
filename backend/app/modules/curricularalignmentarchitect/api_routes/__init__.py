"""Combined API router for CurricularAlignmentArchitect."""

from fastapi import APIRouter

from .agentic_analysis import register_routes as register_agentic_routes
from .analysis import register_routes as register_analysis_routes
from .book_selection import register_routes as register_book_selection_routes
from .book_skill_mapping import register_routes as register_book_skill_mapping_routes
from .chapter_analysis import register_routes as register_chapter_analysis_routes
from .extraction_inspector import (
    register_routes as register_extraction_inspector_routes,
)
from .recommendations import register_routes as register_recommendations_routes
from .skill_prerequisites import register_routes as register_skill_prerequisites_routes

router = APIRouter(prefix="/book-selection", tags=["book_selection"])
register_book_selection_routes(router)
register_analysis_routes(router)
register_agentic_routes(router)
register_chapter_analysis_routes(router)
register_extraction_inspector_routes(router)
register_recommendations_routes(router)
register_book_skill_mapping_routes(router)
register_skill_prerequisites_routes(router)

__all__ = ["router"]
