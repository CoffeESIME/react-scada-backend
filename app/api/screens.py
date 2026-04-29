"""
CRUD de pantallas y layouts SCADA.
Maneja la persistencia de los diagramas de React Flow y la compartición entre usuarios.
"""
import re
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from app.db.session import get_session
from app.db.models import Screen, ScreenAccess, User, ScreenAccessRole
from app.schemas.scada import ScreenCreate, ScreenRead, ScreenUpdate, ScreenListItem, ScreenShareRequest, ScreenShareResponse
from app.users import current_active_user, current_admin_user

router = APIRouter(prefix="/screens", tags=["screens"])


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text

async def _check_screen_access(session: AsyncSession, screen: Screen, user: User, require_editor: bool = False) -> str:
    """Verifica el acceso y retorna el rol (OWNER, VIEWER, EDITOR). Lanza 403 si es denegado."""
    if screen.owner_id is None or screen.owner_id == user.id:
        return "OWNER"
    
    stmt = select(ScreenAccess).where(
        ScreenAccess.screen_id == screen.id,
        ScreenAccess.user_id == user.id
    )
    result = await session.execute(stmt)
    access = result.scalar_one_or_none()
    
    if not access:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta pantalla.")
        
    if require_editor and access.role != ScreenAccessRole.EDITOR:
        raise HTTPException(status_code=403, detail="No tienes permisos para editar esta pantalla.")
        
    return access.role.value


@router.get("/", response_model=List[ScreenListItem])
async def list_screens(
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    stmt = select(Screen).outerjoin(ScreenAccess, Screen.id == ScreenAccess.screen_id).where(
        or_(
            Screen.owner_id == user.id,
            ScreenAccess.user_id == user.id,
            Screen.owner_id.is_(None)
        )
    ).offset(skip).limit(limit).order_by(Screen.name).distinct()
    
    result = await session.execute(stmt)
    screens = result.scalars().all()
    
    responses = []
    # Anotar rol para cada pantalla devuelta
    for screen in screens:
        if screen.owner_id is None or screen.owner_id == user.id:
            role = "OWNER"
        else:
            acc_stmt = select(ScreenAccess).where(ScreenAccess.screen_id == screen.id, ScreenAccess.user_id == user.id)
            acc_res = await session.execute(acc_stmt)
            acc = acc_res.scalar_one_or_none()
            role = acc.role.value if acc else "VIEWER"
            
        data = screen.model_dump()
        data["access_role"] = role
        responses.append(ScreenListItem(**data))

    return responses


@router.post("/", response_model=ScreenRead, status_code=status.HTTP_201_CREATED)
async def create_screen(
    screen_data: ScreenCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    slug = screen_data.slug or slugify(screen_data.name)
    
    existing = await session.execute(select(Screen).where(Screen.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una pantalla con slug '{slug}'")
    
    existing_name = await session.execute(select(Screen).where(Screen.name == screen_data.name))
    if existing_name.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una pantalla con nombre '{screen_data.name}'")
    
    if screen_data.is_home:
        await _clear_current_home(session)
    
    screen = Screen(
        name=screen_data.name,
        slug=slug,
        description=screen_data.description,
        is_home=screen_data.is_home,
        layout_data=screen_data.layout_data,
        owner_id=user.id
    )
    
    session.add(screen)
    await session.commit()
    await session.refresh(screen)
    
    data = screen.model_dump()
    data["access_role"] = "OWNER"
    return ScreenRead(**data)


@router.get("/home", response_model=ScreenRead)
async def get_home_screen(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.is_home == True))
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay pantalla home configurada")
    
    role = await _check_screen_access(session, screen, user)
    data = screen.model_dump()
    data["access_role"] = role
    return ScreenRead(**data)


@router.get("/{slug_or_id}", response_model=ScreenRead)
async def get_screen(
    slug_or_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    screen = await _get_screen_by_slug_or_id(session, slug_or_id)
    if not screen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pantalla '{slug_or_id}' no encontrada")
    
    role = await _check_screen_access(session, screen, user)
    data = screen.model_dump()
    data["access_role"] = role
    return ScreenRead(**data)


@router.put("/{screen_id}", response_model=ScreenRead)
async def update_screen(
    screen_id: int,
    screen_data: ScreenUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.id == screen_id))
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pantalla con ID {screen_id} no encontrada")
        
    role = await _check_screen_access(session, screen, user, require_editor=True)
    
    if screen_data.slug and screen_data.slug != screen.slug:
        existing = await session.execute(select(Screen).where(Screen.slug == screen_data.slug, Screen.id != screen_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una pantalla con slug '{screen_data.slug}'")
    
    if screen_data.name and screen_data.name != screen.name:
        existing = await session.execute(select(Screen).where(Screen.name == screen_data.name, Screen.id != screen_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una pantalla con nombre '{screen_data.name}'")
    
    if screen_data.is_home is True and not screen.is_home:
        await _clear_current_home(session, exclude_id=screen_id)
    
    update_data = screen_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(screen, field, value)
    
    await session.commit()
    await session.refresh(screen)
    
    data = screen.model_dump()
    data["access_role"] = role
    return ScreenRead(**data)


@router.delete("/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screen(
    screen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.id == screen_id))
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pantalla con ID {screen_id} no encontrada")
        
    if screen.owner_id is not None and screen.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede eliminar la pantalla")
    
    await session.delete(screen)
    await session.commit()
    return None

# ============ Compartir Pantallas ============

@router.post("/{screen_id}/share", response_model=ScreenShareResponse)
async def share_screen(
    screen_id: int,
    share_data: ScreenShareRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.id == screen_id))
    screen = result.scalar_one_or_none()
    if not screen: raise HTTPException(404, "Pantalla no encontrada")
    
    if screen.owner_id is not None and screen.owner_id != user.id:
        raise HTTPException(403, "Solo el dueño puede compartir la pantalla")
        
    target_res = await session.execute(
        select(User).where(or_(User.username == share_data.username_or_email, User.email == share_data.username_or_email))
    )
    target_user = target_res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "Usuario no encontrado")
        
    if target_user.id == screen.owner_id:
        raise HTTPException(400, "El dueño ya tiene acceso")
        
    acc_res = await session.execute(
        select(ScreenAccess).where(ScreenAccess.screen_id == screen.id, ScreenAccess.user_id == target_user.id)
    )
    access = acc_res.scalar_one_or_none()
    
    if access:
        access.role = share_data.role
    else:
        access = ScreenAccess(screen_id=screen.id, user_id=target_user.id, role=share_data.role)
        session.add(access)
        
    await session.commit()
    await session.refresh(access)
    
    return ScreenShareResponse(
        id=access.id,
        screen_id=access.screen_id,
        user_id=access.user_id,
        role=access.role,
        username=target_user.username,
        email=target_user.email
    )

@router.get("/{screen_id}/shares", response_model=List[ScreenShareResponse])
async def get_screen_shares(
    screen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.id == screen_id))
    screen = result.scalar_one_or_none()
    if not screen: raise HTTPException(404, "Pantalla no encontrada")
    
    if screen.owner_id is not None and screen.owner_id != user.id:
        raise HTTPException(403, "Solo el dueño puede ver a quién está compartida")
        
    acc_res = await session.execute(
        select(ScreenAccess, User).join(User, ScreenAccess.user_id == User.id).where(ScreenAccess.screen_id == screen_id)
    )
    shares = acc_res.all()
    
    responses = []
    for acc, usr in shares:
        responses.append(ScreenShareResponse(
            id=acc.id,
            screen_id=acc.screen_id,
            user_id=acc.user_id,
            role=acc.role,
            username=usr.username,
            email=usr.email
        ))
    return responses

@router.delete("/{screen_id}/share/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_screen_share(
    screen_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_session),
    owner: User = Depends(current_active_user)
):
    result = await session.execute(select(Screen).where(Screen.id == screen_id))
    screen = result.scalar_one_or_none()
    if not screen: raise HTTPException(404, "Pantalla no encontrada")
    
    if screen.owner_id is not None and screen.owner_id != owner.id:
        raise HTTPException(403, "Solo el dueño puede revocar accesos")
        
    acc_res = await session.execute(
        select(ScreenAccess).where(ScreenAccess.screen_id == screen_id, ScreenAccess.user_id == user_id)
    )
    access = acc_res.scalar_one_or_none()
    if access:
        await session.delete(access)
        await session.commit()
    return None

# ============ Helper Functions ============

async def _clear_current_home(
    session: AsyncSession, 
    exclude_id: int = None
):
    stmt = select(Screen).where(Screen.is_home == True)
    if exclude_id:
        stmt = stmt.where(Screen.id != exclude_id)
    
    result = await session.execute(stmt)
    current_home = result.scalar_one_or_none()
    
    if current_home:
        current_home.is_home = False
        await session.flush()


async def _get_screen_by_slug_or_id(
    session: AsyncSession, 
    slug_or_id: str
) -> Screen | None:
    if slug_or_id.isdigit():
        result = await session.execute(
            select(Screen).where(Screen.id == int(slug_or_id))
        )
        screen = result.scalar_one_or_none()
        if screen:
            return screen
    
    result = await session.execute(
        select(Screen).where(Screen.slug == slug_or_id)
    )
    return result.scalar_one_or_none()
