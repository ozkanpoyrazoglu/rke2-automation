from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Credential, CredentialType
from app.schemas import (
    CredentialCreate,
    CredentialResponse,
    AccessCheckRequest,
    AccessCheckResponse
)
from app.services.encryption_service import encrypt_secret, decrypt_secret
from app.services.access_check_service import run_access_check

router = APIRouter()

@router.post("", response_model=CredentialResponse)
async def create_credential(
    credential: CredentialCreate,
    db: Session = Depends(get_db)
):
    """Create a new SSH credential (encrypted)"""
    existing = db.query(Credential).filter(Credential.name == credential.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Credential name already exists")

    # Encrypt the secret before storing
    encrypted_secret = encrypt_secret(credential.secret)

    new_credential = Credential(
        name=credential.name,
        username=credential.username,
        credential_type=credential.credential_type,
        encrypted_secret=encrypted_secret
    )

    db.add(new_credential)
    db.commit()
    db.refresh(new_credential)

    return new_credential

@router.get("", response_model=List[CredentialResponse])
async def list_credentials(db: Session = Depends(get_db)):
    """List all credentials (without secrets)"""
    credentials = db.query(Credential).all()
    return credentials

@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: int, db: Session = Depends(get_db)):
    """Get credential details (without secret)"""
    credential = db.query(Credential).filter(Credential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return credential

@router.delete("/{credential_id}")
async def delete_credential(credential_id: int, db: Session = Depends(get_db)):
    """Delete a credential"""
    credential = db.query(Credential).filter(Credential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Check if credential is in use
    if credential.clusters:
        raise HTTPException(
            status_code=400,
            detail=f"Credential is in use by {len(credential.clusters)} cluster(s)"
        )

    db.delete(credential)
    db.commit()
    return {"message": "Credential deleted"}

@router.post("/test-access", response_model=AccessCheckResponse)
async def test_access(
    request: AccessCheckRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Test SSH access to hosts using a credential
    Runs check_access.yml playbook
    """
    credential = db.query(Credential).filter(Credential.id == request.credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Run access check in background
    result = await run_access_check(credential, request.hosts)
    return result
