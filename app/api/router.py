from fastapi import APIRouter

from app.api.routes import admin, me, public, webhooks

api_router = APIRouter()
api_router.include_router(public.router)
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(webhooks.router)
