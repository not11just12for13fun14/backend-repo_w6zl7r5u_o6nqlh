"""
Database Schemas for Nail Salon Booking System

Each Pydantic model maps to a MongoDB collection using the lowercase class name.
Examples:
- Client -> "client"
- Staff -> "staff"
- Service -> "service"
- Appointment -> "appointment"
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import datetime


class Client(BaseModel):
    """
    Clients of the salon
    Collection: client
    """
    name: str = Field(..., description="Full name of the client")
    phone: str = Field(..., description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Email address")
    notes: Optional[str] = Field(None, description="Additional notes about client preferences or allergies")


class Staff(BaseModel):
    """
    Salon staff (technicians)
    Collection: staff
    """
    name: str = Field(..., description="Staff member name")
    specialties: List[str] = Field(default_factory=list, description="List of service specialties e.g. 'Gel', 'Acrylic'")
    active: bool = Field(default=True, description="Whether the staff member is currently active")


class Service(BaseModel):
    """
    Services offered by the salon
    Collection: service
    """
    name: str = Field(..., description="Service name e.g. 'Gel Manicure'")
    description: Optional[str] = Field(None, description="Service description")
    duration_minutes: int = Field(..., ge=5, le=480, description="Duration of the service in minutes")
    price: float = Field(..., ge=0, description="Price in USD")
    active: bool = Field(default=True, description="Whether the service is available")


class Appointment(BaseModel):
    """
    Appointments linking client, staff, and service
    Collection: appointment
    """
    client_id: str = Field(..., description="ID of the client")
    staff_id: str = Field(..., description="ID of the staff member")
    service_id: str = Field(..., description="ID of the service")
    start_time: datetime = Field(..., description="Appointment start time (UTC or local ISO)")
    end_time: Optional[datetime] = Field(None, description="Appointment end time; computed from duration if not provided")
    status: Literal["booked", "canceled", "completed"] = Field("booked", description="Status of appointment")
    notes: Optional[str] = Field(None, description="Optional notes for this appointment")
