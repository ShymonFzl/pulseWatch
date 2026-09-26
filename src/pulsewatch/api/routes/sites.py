"""Management of the monitored sites."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from pulsewatch.api.dependencies import SessionDep
from pulsewatch.api.schemas import ErrorResponse, SiteCreate, SiteRead
from pulsewatch.db.models import Site

router = APIRouter(prefix="/sites", tags=["sites"])

# Upper bound of PostgreSQL bigint: larger values would fail in the database (500).
BIGINT_MAX = 2**63 - 1

SiteId = Annotated[int, Path(gt=0, le=BIGINT_MAX)]

NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


def _violated_constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def create_site(
    payload: SiteCreate, session: SessionDep, request: Request, response: Response
) -> SiteRead:
    site = Site(name=payload.name, url=str(payload.url))
    session.add(site)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # The unique constraint decides, which is safe under concurrent requests.
        if _violated_constraint(exc) == "uq_sites_url":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "A site with this URL already exists"
            ) from exc
        raise
    await session.refresh(site)
    response.headers["Location"] = str(request.url_for("get_site", site_id=site.id))
    return SiteRead.model_validate(site)


@router.get("")
async def list_sites(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=BIGINT_MAX)] = 0,
) -> list[SiteRead]:
    sites = await session.scalars(select(Site).order_by(Site.id).limit(limit).offset(offset))
    return [SiteRead.model_validate(site) for site in sites]


@router.get("/{site_id}", responses=NOT_FOUND)
async def get_site(site_id: SiteId, session: SessionDep) -> SiteRead:
    site = await session.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return SiteRead.model_validate(site)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_site(site_id: SiteId, session: SessionDep) -> None:
    # Its checks are removed by ON DELETE CASCADE.
    deleted = await session.scalar(delete(Site).where(Site.id == site_id).returning(Site.id))
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    await session.commit()
