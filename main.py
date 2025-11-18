import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Client, Staff, Service, Appointment


# ---------- Utils ----------

def oid(obj) -> str:
    try:
        return str(obj)
    except Exception:
        return obj


def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    d = {**doc}
    if d.get("_id") is not None:
        d["id"] = str(d.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ---------- FastAPI App ----------

app = FastAPI(title="Nail Salon Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Health ----------

@app.get("/")
def read_root():
    return {"message": "Nail Salon Booking API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is None:
            response["database"] = "❌ Not Connected"
        else:
            response["database"] = "✅ Connected & Working"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ---------- Request Models ----------

class ClientCreate(Client):
    pass


class StaffCreate(Staff):
    pass


class ServiceCreate(Service):
    pass


class AppointmentCreate(BaseModel):
    client_id: str = Field(...)
    staff_id: str = Field(...)
    service_id: str = Field(...)
    start_time: datetime = Field(...)
    notes: Optional[str] = None


class AppointmentStatusUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(booked|canceled|completed)$")
    notes: Optional[str] = None


# ---------- Helper logic ----------

def ensure_exists(collection: str, _id: str, label: str):
    try:
        doc = db[collection].find_one({"_id": ObjectId(_id)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return doc


def compute_end(start: datetime, duration_minutes: int) -> datetime:
    return start + timedelta(minutes=duration_minutes)


def has_overlap(staff_id: str, start: datetime, end: datetime, exclude_id: Optional[str] = None) -> bool:
    query = {
        "staff_id": staff_id,
        "status": {"$in": ["booked", "completed"]},  # completed still blocks that time historically
        "$or": [
            {"start_time": {"$lt": end}, "end_time": {"$gt": start}},  # core overlap condition
        ],
    }
    if exclude_id:
        query["_id"] = {"$ne": ObjectId(exclude_id)}
    return db["appointment"].count_documents(query) > 0


# ---------- Clients ----------

@app.get("/api/clients")
def list_clients():
    docs = get_documents("client")
    return [serialize_doc(d) for d in docs]


@app.post("/api/clients", status_code=201)
def create_client(payload: ClientCreate):
    new_id = create_document("client", payload)
    doc = db["client"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# ---------- Staff ----------

@app.get("/api/staff")
def list_staff():
    docs = get_documents("staff")
    return [serialize_doc(d) for d in docs]


@app.post("/api/staff", status_code=201)
def create_staff(payload: StaffCreate):
    new_id = create_document("staff", payload)
    doc = db["staff"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# ---------- Services ----------

@app.get("/api/services")
def list_services():
    docs = get_documents("service", {"active": True})
    return [serialize_doc(d) for d in docs]


@app.post("/api/services", status_code=201)
def create_service(payload: ServiceCreate):
    new_id = create_document("service", payload)
    doc = db["service"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# ---------- Appointments ----------

@app.get("/api/appointments")
def list_appointments(
    date: Optional[str] = Query(None, description="YYYY-MM-DD to filter by day"),
    staff_id: Optional[str] = Query(None),
):
    filt = {}
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
        start = day
        end = day + timedelta(days=1)
        filt.update({"start_time": {"$gte": start, "$lt": end}})
    if staff_id:
        filt["staff_id"] = staff_id
    docs = db["appointment"].find(filt).sort("start_time", 1)
    return [serialize_doc(d) for d in docs]


@app.post("/api/appointments", status_code=201)
def create_appointment(payload: AppointmentCreate):
    # Validate related entities
    client = ensure_exists("client", payload.client_id, "Client")
    staff = ensure_exists("staff", payload.staff_id, "Staff")
    service = ensure_exists("service", payload.service_id, "Service")

    # Compute end_time from service duration
    duration = service.get("duration_minutes", 60)
    start_time = payload.start_time
    end_time = compute_end(start_time, duration)

    # Overlap check for staff schedule
    if has_overlap(payload.staff_id, start_time, end_time):
        raise HTTPException(status_code=409, detail="Time slot overlaps another appointment for this staff member")

    appt = Appointment(
        client_id=payload.client_id,
        staff_id=payload.staff_id,
        service_id=payload.service_id,
        start_time=start_time,
        end_time=end_time,
        status="booked",
        notes=payload.notes,
    )

    new_id = create_document("appointment", appt)
    created = db["appointment"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(created)


@app.patch("/api/appointments/{appointment_id}")
def update_appointment_status(appointment_id: str, payload: AppointmentStatusUpdate):
    doc = db["appointment"].find_one({"_id": ObjectId(appointment_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Appointment not found")

    updates = {}
    if payload.status:
        updates["status"] = payload.status
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if not updates:
        return serialize_doc(doc)

    updates["updated_at"] = datetime.utcnow()
    db["appointment"].update_one({"_id": ObjectId(appointment_id)}, {"$set": updates})
    doc = db["appointment"].find_one({"_id": ObjectId(appointment_id)})
    return serialize_doc(doc)


# Simple hello for sanity
@app.get("/api/hello")
def hello():
    return {"message": "Hello from the nail salon backend!"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
