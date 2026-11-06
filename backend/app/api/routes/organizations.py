
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationResponse


# Cria um router para os endpoints de organizações.
router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    organization_data: OrganizationCreate,
    db: Session = Depends(get_db),
):
    # 1. Verificar se já existe uma organização com este slug.
    existing_organization = db.scalar(
        select(Organization).where(
            Organization.slug == organization_data.slug
        )
    )

    if existing_organization:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists.",
        )

    # 2. Criar um objeto SQLAlchemy.
    organization = Organization(
        name=organization_data.name,
        slug=organization_data.slug,
    )

    # 3. Adicionar o objeto à sessão.
    db.add(organization)

    try:
        # 4. Confirmar a transação na PostgreSQL.
        db.commit()

    except IntegrityError:
        # Desfazer a transação se ocorrer um conflito na base de dados.
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists.",
        )

    # 5. Atualizar o objeto com os dados persistidos.
    db.refresh(organization)

    # 6. Devolver o objeto; FastAPI aplica OrganizationResponse.
    return organization
