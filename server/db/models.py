from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    """Users who have installed the Chrome extension and logged in with Google."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    google_access_token = Column(Text)
    google_refresh_token = Column(Text)
    token_expiry = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    organized_meetings = relationship("Meeting", back_populates="organizer", cascade="all, delete-orphan")
    invites = relationship("MeetingInvite", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Session(Base):
    """Active login sessions."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    session_token = Column(String(255), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="sessions")


class Meeting(Base):
    """
    Meeting requests created by users.

    Flow:
    1. User creates meeting with title, duration, urgency, location, invited members
    2. Algorithm optimizes to find best time (status: optimizing)
    3. Once optimized, invites are sent (status: scheduled)
    4. Meeting completes or is cancelled
    """
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True)
    organizer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Meeting details (input by user)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False)
    urgency = Column(String(20), nullable=False, default="normal")  # low, normal, high, urgent
    location = Column(String(255))  # physical location or 'virtual'

    # Optimized result (set by algorithm)
    scheduled_start = Column(DateTime(timezone=True))
    scheduled_end = Column(DateTime(timezone=True))
    final_location = Column(String(255))

    # Status tracking
    status = Column(String(50), default="pending")  # pending, optimizing, scheduled, completed, cancelled

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organizer = relationship("User", back_populates="organized_meetings")
    invites = relationship("MeetingInvite", back_populates="meeting", cascade="all, delete-orphan")

    def to_dict(self, include_invites=True):
        data = {
            "id": self.id,
            "organizer_id": self.organizer_id,
            "organizer_email": self.organizer.email if self.organizer else None,
            "title": self.title,
            "description": self.description,
            "duration_minutes": self.duration_minutes,
            "urgency": self.urgency,
            "location": self.location,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "scheduled_end": self.scheduled_end.isoformat() if self.scheduled_end else None,
            "final_location": self.final_location,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_invites:
            data["invites"] = [inv.to_dict() for inv in self.invites]
        return data


class MeetingInvite(Base):
    """
    Meeting invites for each user.

    When a user opens the Chrome extension, they see all their pending invites
    and can accept or decline them.
    """
    __tablename__ = "meeting_invites"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Invite status
    status = Column(String(50), default="pending")  # pending, accepted, declined
    is_required = Column(Boolean, default=True)  # required vs optional attendee

    # Timestamps
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at = Column(DateTime(timezone=True))

    meeting = relationship("Meeting", back_populates="invites")
    user = relationship("User", back_populates="invites")

    def to_dict(self):
        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "user_id": self.user_id,
            "email": self.user.email if self.user else None,
            "name": self.user.name if self.user else None,
            "status": self.status,
            "is_required": self.is_required,
            "invited_at": self.invited_at.isoformat() if self.invited_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }
