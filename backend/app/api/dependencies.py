from typing import Annotated

from fastapi import Query

from app.core.config import settings

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=settings.max_page_size)]
