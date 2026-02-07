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
    organized_proposals = relationship("MeetingProposal", back_populates="organizer", cascade="all, delete-orphan")
    confirmed_meetings = relationship("ConfirmedMeeting", back_populates="organizer", cascade="all, delete-orphan")
    proposal_invites = relationship("MeetingInvite", back_populates="user", cascade="all, delete-orphan")
    confirmed_invites = relationship("ConfirmedMeetingInvite", back_populates="user", cascade="all, delete-orphan")

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


class MeetingProposal(Base):
    """
    Meeting proposals created by users.

    Flow:
    1. User creates proposal with title, duration, urgency, location, invited members, windows
    2. Algorithm optimizes to find best time (status: optimizing)
    3. Proposal is confirmed into a scheduled meeting
    4. Proposal is completed or cancelled
    """
    __tablename__ = "meeting_proposals"

    id = Column(Integer, primary_key=True)
    organizer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Meeting details (input by user)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False)
    urgency = Column(String(20), nullable=False, default="normal")  # low, normal, high, urgent
    location = Column(String(255))  # physical location or 'virtual'

    # Scheduling windows (input by user)
    window_start = Column(DateTime(timezone=True))
    window_end = Column(DateTime(timezone=True))

    # Status tracking
    status = Column(String(50), default="pending")  # pending, optimizing, confirmed, cancelled

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organizer = relationship("User", back_populates="organized_proposals")
    invites = relationship("MeetingInvite", back_populates="proposal", cascade="all, delete-orphan")
    confirmed_meeting = relationship(
        "ConfirmedMeeting",
        back_populates="proposal",
        uselist=False,
        cascade="all, delete-orphan",
    )

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
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_invites:
            data["invites"] = [inv.to_dict() for inv in self.invites]
        if self.confirmed_meeting:
            data["confirmed_meeting"] = self.confirmed_meeting.to_dict(include_invites=False)
        return data


class ConfirmedMeeting(Base):
    """
    Confirmed meetings derived from proposals.
    Windows are replaced with concrete start/end times.
    """
    __tablename__ = "confirmed_meetings"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("meeting_proposals.id", ondelete="CASCADE"), unique=True)
    organizer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Meeting details (copied from proposal at confirmation time)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False)
    urgency = Column(String(20), nullable=False, default="normal")  # low, normal, high, urgent
    location = Column(String(255))  # physical location or 'virtual'

    # Confirmed schedule
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    final_location = Column(String(255))

    # Status tracking
    status = Column(String(50), default="scheduled")  # scheduled, completed, cancelled

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organizer = relationship("User", back_populates="confirmed_meetings")
    proposal = relationship("MeetingProposal", back_populates="confirmed_meeting")
    invites = relationship("ConfirmedMeetingInvite", back_populates="meeting", cascade="all, delete-orphan")

    def to_dict(self, include_invites=True):
        return {
            "id": self.id,
            "proposal_id": self.proposal_id,
            "organizer_id": self.organizer_id,
            "title": self.title,
            "description": self.description,
            "duration_minutes": self.duration_minutes,
            "urgency": self.urgency,
            "location": self.location,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "final_location": self.final_location,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "invites": [inv.to_dict() for inv in self.invites] if include_invites else [],
        }


class MeetingInvite(Base):
    """
    Meeting proposal invites for each user.

    When a user opens the Chrome extension, they see all their pending invites
    and can accept or decline them.
    """
    __tablename__ = "meeting_invites"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("meeting_proposals.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Invite status
    status = Column(String(50), default="pending")  # pending, accepted, declined
    is_required = Column(Boolean, default=True)  # required vs optional attendee

    # Timestamps
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at = Column(DateTime(timezone=True))

    proposal = relationship("MeetingProposal", back_populates="invites")
    user = relationship("User", back_populates="proposal_invites")

    def to_dict(self):
        return {
            "id": self.id,
            "proposal_id": self.proposal_id,
            "user_id": self.user_id,
            "email": self.user.email if self.user else None,
            "name": self.user.name if self.user else None,
            "status": self.status,
            "is_required": self.is_required,
            "invited_at": self.invited_at.isoformat() if self.invited_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }


class ConfirmedMeetingInvite(Base):
    """
    Confirmed meeting invites for each user.
    """
    __tablename__ = "confirmed_meeting_invites"

    id = Column(Integer, primary_key=True)
    confirmed_meeting_id = Column(Integer, ForeignKey("confirmed_meetings.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Invite status
    status = Column(String(50), default="pending")  # pending, accepted, declined
    is_required = Column(Boolean, default=True)  # required vs optional attendee

    # Timestamps
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at = Column(DateTime(timezone=True))

    meeting = relationship("ConfirmedMeeting", back_populates="invites")
    user = relationship("User", back_populates="confirmed_invites")

    def to_dict(self):
        return {
            "id": self.id,
            "confirmed_meeting_id": self.confirmed_meeting_id,
            "user_id": self.user_id,
            "email": self.user.email if self.user else None,
            "name": self.user.name if self.user else None,
            "status": self.status,
            "is_required": self.is_required,
            "invited_at": self.invited_at.isoformat() if self.invited_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }


class Notification(Base):
    """
    LinkedIn-style notifications for meeting confirmations.
    Sent to invitees (not the host) when a meeting is confirmed by the algorithm.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    confirmed_meeting_id = Column(Integer, ForeignKey("confirmed_meetings.id", ondelete="CASCADE"))

    # Notification type and content
    type = Column(String(50), nullable=False, default="meeting_confirmed")
    title = Column(String(255), nullable=False)
    message = Column(Text)

    # Status tracking
    is_read = Column(Boolean, default=False)
    response = Column(String(50))  # accepted, declined, null if not responded

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at = Column(DateTime(timezone=True))

    user = relationship("User", backref="notifications")
    confirmed_meeting = relationship("ConfirmedMeeting", backref="notifications")

    def to_dict(self):
        meeting = self.confirmed_meeting
        organizer = meeting.organizer if meeting else None
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "response": self.response,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "meeting": {
                "id": meeting.id,
                "title": meeting.title,
                "start_time": meeting.start_time.isoformat() if meeting.start_time else None,
                "end_time": meeting.end_time.isoformat() if meeting.end_time else None,
                "location": meeting.final_location or meeting.location,
                "organizer_name": organizer.name if organizer else None,
                "organizer_email": organizer.email if organizer else None,
            } if meeting else None,
        }
