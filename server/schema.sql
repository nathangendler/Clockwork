-- Clockwork Database Schema
-- Run this to initialize your PostgreSQL database

-- Create the database (run this separately as postgres superuser)
-- CREATE DATABASE clockwork;

-- ============================================
-- USERS TABLE
-- Stores all users who have the Chrome extension installed
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    google_access_token TEXT,
    google_refresh_token TEXT,
    token_expiry TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- SESSIONS TABLE
-- Stores active login sessions
-- ============================================
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- ============================================
-- MEETING PROPOSALS TABLE
-- Stores meeting proposals created by users
-- Status flow: pending → optimizing → confirmed/cancelled
-- ============================================
CREATE TABLE IF NOT EXISTS meeting_proposals (
    id SERIAL PRIMARY KEY,
    organizer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Meeting details (input by user)
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration_minutes INTEGER NOT NULL,
    urgency VARCHAR(20) NOT NULL DEFAULT 'normal',  -- low, normal, high, urgent
    location VARCHAR(255),  -- physical location or 'virtual'

    -- Scheduling windows (input by user)
    window_start TIMESTAMP WITH TIME ZONE,
    window_end TIMESTAMP WITH TIME ZONE,

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',  -- pending, optimizing, confirmed, cancelled

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- CONFIRMED MEETINGS TABLE
-- Stores confirmed meetings derived from proposals
-- ============================================
CREATE TABLE IF NOT EXISTS confirmed_meetings (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER UNIQUE REFERENCES meeting_proposals(id) ON DELETE CASCADE,
    organizer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Meeting details (copied from proposal at confirmation time)
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration_minutes INTEGER NOT NULL,
    urgency VARCHAR(20) NOT NULL DEFAULT 'normal',  -- low, normal, high, urgent
    location VARCHAR(255),  -- physical location or 'virtual'

    -- Confirmed schedule
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    final_location VARCHAR(255),

    -- Status tracking
    status VARCHAR(50) DEFAULT 'scheduled',  -- scheduled, completed, cancelled

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- MEETING INVITES TABLE
-- Stores proposal invites for each user
-- When user opens extension, they see all their pending invites
-- ============================================
CREATE TABLE IF NOT EXISTS meeting_invites (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER REFERENCES meeting_proposals(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Invite status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, accepted, declined
    is_required BOOLEAN DEFAULT TRUE,  -- required vs optional attendee

    -- Timestamps
    invited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP WITH TIME ZONE,

    UNIQUE(proposal_id, user_id)
);

-- ============================================
-- CONFIRMED MEETING INVITES TABLE
-- Stores confirmed meeting invites for each user
-- ============================================
CREATE TABLE IF NOT EXISTS confirmed_meeting_invites (
    id SERIAL PRIMARY KEY,
    confirmed_meeting_id INTEGER REFERENCES confirmed_meetings(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Invite status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, accepted, declined
    is_required BOOLEAN DEFAULT TRUE,  -- required vs optional attendee

    -- Timestamps
    invited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP WITH TIME ZONE,

    UNIQUE(confirmed_meeting_id, user_id)
);

-- ============================================
-- NOTIFICATIONS TABLE
-- LinkedIn-style notifications for meeting confirmations
-- Sent to invitees (not host) when meeting is confirmed
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    confirmed_meeting_id INTEGER REFERENCES confirmed_meetings(id) ON DELETE CASCADE,

    -- Notification type and content
    type VARCHAR(50) NOT NULL DEFAULT 'meeting_confirmed',  -- meeting_confirmed, meeting_updated, etc.
    title VARCHAR(255) NOT NULL,
    message TEXT,

    -- Status tracking
    is_read BOOLEAN DEFAULT FALSE,
    response VARCHAR(50),  -- accepted, declined, null if not responded

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP WITH TIME ZONE
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_meeting_proposals_organizer ON meeting_proposals(organizer_id);
CREATE INDEX IF NOT EXISTS idx_meeting_proposals_status ON meeting_proposals(status);
CREATE INDEX IF NOT EXISTS idx_confirmed_meetings_organizer ON confirmed_meetings(organizer_id);
CREATE INDEX IF NOT EXISTS idx_confirmed_meetings_status ON confirmed_meetings(status);
CREATE INDEX IF NOT EXISTS idx_invites_proposal ON meeting_invites(proposal_id);
CREATE INDEX IF NOT EXISTS idx_invites_user ON meeting_invites(user_id);
CREATE INDEX IF NOT EXISTS idx_invites_status ON meeting_invites(status);
CREATE INDEX IF NOT EXISTS idx_confirmed_invites_meeting ON confirmed_meeting_invites(confirmed_meeting_id);
CREATE INDEX IF NOT EXISTS idx_confirmed_invites_user ON confirmed_meeting_invites(user_id);
CREATE INDEX IF NOT EXISTS idx_confirmed_invites_status ON confirmed_meeting_invites(status);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_meeting ON notifications(confirmed_meeting_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
