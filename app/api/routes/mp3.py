from fastapi import APIRouter, Depends
from sqlalchemy import update

from app.core.crud_router import build_crud_router
from app.core.dependencies import DbSession
from app.models.multimedia import Mp3Song
from app.schemas.multimedia import Mp3SongCreate, Mp3SongOut, Mp3SongUpdate

router = build_crud_router(
    model=Mp3Song,
    create_schema=Mp3SongCreate,
    update_schema=Mp3SongUpdate,
    out_schema=Mp3SongOut,
    prefix="/mp3",
    tags=["Multimedia - MP3"],
    resource_label="mp3 songs",
    search_field="title",
)

extra_router = APIRouter(prefix="/mp3", tags=["Multimedia - MP3"])


@extra_router.post("/{item_id}/play", summary="Increment play count")
async def increment_play_count(item_id: int, db: DbSession) -> dict[str, int]:
    await db.execute(update(Mp3Song).where(Mp3Song.id == item_id).values(play_count=Mp3Song.play_count + 1))
    await db.commit()
    return {"item_id": item_id}


@extra_router.post("/{item_id}/download", summary="Increment download count")
async def increment_download_count(item_id: int, db: DbSession) -> dict[str, int]:
    await db.execute(
        update(Mp3Song).where(Mp3Song.id == item_id).values(download_count=Mp3Song.download_count + 1)
    )
    await db.commit()
    return {"item_id": item_id}


# extra_router's paths are 2 segments ("/{item_id}/play") so they never
# collide with the generic router's 1-segment "/{item_id}" — order-independent.
