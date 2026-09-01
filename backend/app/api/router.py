from fastapi import APIRouter

from app.api.routes import admin, auth, me, public

api_router = APIRouter()
api_router.include_router(public.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(admin.router)
