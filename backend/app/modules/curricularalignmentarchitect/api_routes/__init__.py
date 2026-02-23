"""Combined API router for CurricularAlignmentArchitect."""

from fastapi import APIRouter

from .analysis import register_routes as register_analysis_routes
from .book_selection import register_routes as register_book_selection_routes

router = APIRouter(prefix="/book-selection", tags=["book_selection"])
register_book_selection_routes(router)
register_analysis_routes(router)

__all__ = ["router"]
