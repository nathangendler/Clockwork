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
-- MEETINGS TABLE
-- Stores meeting requests created by users
-- Status flow: pending → optimizing → scheduled → completed/cancelled
-- ============================================
CREATE TABLE IF NOT EXISTS meetings (
    id SERIAL PRIMARY KEY,
    organizer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Meeting details (input by user)
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration_minutes INTEGER NOT NULL,
    urgency VARCHAR(20) NOT NULL DEFAULT 'normal',  -- low, normal, high, urgent
    location VARCHAR(255),  -- physical location or 'virtual'

    -- Optimized result (set by algorithm)
    scheduled_start TIMESTAMP WITH TIME ZONE,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    final_location VARCHAR(255),

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',  -- pending, optimizing, scheduled, completed, cancelled

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- MEETING INVITES TABLE
-- Stores invites for each user
-- When user opens extension, they see all their pending invites
-- ============================================
CREATE TABLE IF NOT EXISTS meeting_invites (
    id SERIAL PRIMARY KEY,
    meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Invite status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, accepted, declined
    is_required BOOLEAN DEFAULT TRUE,  -- required vs optional attendee

    -- Timestamps
    invited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP WITH TIME ZONE,

    UNIQUE(meeting_id, user_id)
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_organizer ON meetings(organizer_id);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_invites_meeting ON meeting_invites(meeting_id);
CREATE INDEX IF NOT EXISTS idx_invites_user ON meeting_invites(user_id);
CREATE INDEX IF NOT EXISTS idx_invites_status ON meeting_invites(status);
