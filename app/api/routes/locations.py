from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.inventory import PincodeInventory
from app.models.user import User

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/pincodes")
def search_pincodes(
    q: Optional[str] = Query(default=None, min_length=2),
    city: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PincodeInventory).filter(PincodeInventory.is_available.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (PincodeInventory.pincode.ilike(like))
            | (PincodeInventory.city.ilike(like))
            | (PincodeInventory.district.ilike(like))
            | (PincodeInventory.state.ilike(like))
        )
    if city:
        query = query.filter(PincodeInventory.city.ilike(f"%{city}%"))
    if state:
        query = query.filter(PincodeInventory.state.ilike(f"%{state}%"))

    rows = query.order_by(PincodeInventory.pincode.asc()).limit(limit).all()
    return success_response(
        [
            {
                "pincode": r.pincode,
                "city": r.city,
                "district": r.district,
                "state": r.state,
                "estimated_households": r.estimated_households,
                "estimated_ctv_reach": r.estimated_ctv_reach,
                "avg_cpm": r.avg_cpm,
                "is_estimate": r.is_estimate,
            }
            for r in rows
        ],
        meta={"note": "Reach figures are labeled estimates / demo inventory unless live publisher data is connected."},
    )


@router.get("/states")
def list_states(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(PincodeInventory.state).distinct().order_by(PincodeInventory.state.asc()).all()
    return success_response([r[0] for r in rows if r[0]])


@router.get("/cities")
def list_cities(
    state: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PincodeInventory.city, PincodeInventory.state).distinct()
    if state:
        query = query.filter(PincodeInventory.state == state)
    rows = query.order_by(PincodeInventory.city.asc()).all()
    return success_response([{"city": c, "state": s} for c, s in rows])
