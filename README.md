# Meeting Time Optimizer

An intelligent meeting scheduler that analyzes multiple Google Calendars to find optimal meeting times based on availability, preferences, and organizational policies.

## Features

✅ **Multi-Calendar Analysis** - Aggregate availability from multiple people's calendars  
✅ **Smart Scoring** - Ranks meeting times based on configurable preferences  
✅ **Timezone Support** - Handles participants across different timezones  
✅ **Flexible Configuration** - Customizable work hours, penalties, and bonuses  
✅ **Google Calendar Integration** - Fetch real calendar data via API  
✅ **CLI Interface** - Easy command-line usage

## Quick Start

### 1. Setup

```bash
# Install dependencies
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Make scripts executable (optional)
chmod +x meeting_optimizer.py google_calendar_helper.py
```

### 2. Test with Sample Data

Run the optimizer with the included sample calendars:

```bash
python meeting_optimizer.py \
  --start "2024-03-15T09:00:00-05:00" \
  --end "2024-03-15T17:00:00-05:00" \
  --duration 60 \
  --location virtual
```

### 3. Use with Real Google Calendars

#### Step 1: Get Google Calendar API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Calendar API**
4. Create **OAuth 2.0 credentials** (Desktop application)
5. Download `credentials.json` to this directory

#### Step 2: Fetch Calendar Data

```bash
python google_calendar_helper.py \
  --emails alice@company.com bob@company.com carol@company.com \
  --names "Alice Johnson" "Bob Smith" "Carol Davis" \
  --start "2024-03-15T00:00:00-05:00" \
  --end "2024-03-22T23:59:59-05:00" \
  --output calendars.json
```

This will:
- Open browser for Google OAuth authentication (first time only)
- Fetch all events for specified people
- Save to `calendars.json`

#### Step 3: Find Optimal Meeting Times

```bash
python meeting_optimizer.py \
  --start "2024-03-15T09:00:00-05:00" \
  --end "2024-03-15T17:00:00-05:00" \
  --duration 60 \
  --calendars calendars.json
```

## Usage Examples

### Find a 30-minute slot for today

```bash
python meeting_optimizer.py \
  --start "2024-03-15T09:00:00-05:00" \
  --end "2024-03-15T17:00:00-05:00" \
  --duration 30
```

### Find in-person meeting slot this week

```bash
python meeting_optimizer.py \
  --start "2024-03-15T09:00:00-05:00" \
  --end "2024-03-19T17:00:00-05:00" \
  --duration 60 \
  --location in-person \
  --top 10
```

### Get results as JSON

```bash
python meeting_optimizer.py \
  --start "2024-03-15T09:00:00-05:00" \
  --end "2024-03-15T17:00:00-05:00" \
  --json-output > results.json
```

## Configuration

### Organization Settings (`org_settings.json`)

Customize your organization's preferences:

```json
{
  "work_hours": {
    "start": 540,    // 9:00 AM (minutes from midnight)
    "end": 1020      // 5:00 PM
  },
  "lunch_window": {
    "start": 720,    // 12:00 PM
    "end": 780       // 1:00 PM
  },
  "penalties": {
    "outside_work_hours": 50,
    "overlaps_lunch": 30,
    "early_morning": 20,
    "weekend": 40
  },
  "bonuses": {
    "optimal_time_slot": 15,
    "monday_morning": 10,
    "virtual_meeting": 5
  }
}
```

### Calendar Data Format (`calendars.json`)

```json
[
  {
    "id": "alice",
    "name": "Alice Johnson",
    "email": "alice@company.com",
    "timezone": "America/New_York",
    "preferences": {
      "preferred_meeting_times": ["morning"],
      "avoid_back_to_back": true,
      "min_break_minutes": 15
    },
    "events": [
      {
        "start": {"dateTime": "2024-03-15T10:00:00-05:00"},
        "end": {"dateTime": "2024-03-15T11:00:00-05:00"},
        "summary": "Team Standup"
      }
    ]
  }
]
```

## Scoring Algorithm

The optimizer scores each available slot (0-100) based on:

### Bonuses 🎁
- **Optimal time slots** (+15): 10-11 AM or 2-3 PM
- **Monday morning** (+10): Fresh start to the week
- **Virtual meetings** (+5): More flexibility
- **In-person midday** (+5): Best time for office meetings

### Penalties ⚠️
- **Outside work hours** (-50): Before 9 AM or after 5 PM
- **Weekend** (-40): Saturday or Sunday
- **Lunch overlap** (-30): 12-1 PM
- **Late evening** (-25): After 4 PM
- **Early morning** (-20): Before 10 AM
- **Friday afternoon** (-15): End-of-week fatigue
- **Additional timezones** (-5 each): Cross-timezone coordination

## Command-Line Options

### Required
- `--start`: Meeting window start time (ISO format)
- `--end`: Meeting window end time (ISO format)

### Optional
- `--duration`: Meeting duration in minutes (default: 60)
- `--location`: Meeting type: `virtual`, `in-person`, or `hybrid` (default: virtual)
- `--calendars`: Path to calendar data JSON (default: calendars.json)
- `--org-settings`: Path to org settings JSON (default: org_settings.json)
- `--timezone`: Default timezone (default: America/New_York)
- `--top`: Number of top slots to return (default: 5)
- `--json-output`: Output results as JSON

## Output Example

```
======================================================================
🎯 OPTIMAL MEETING TIMES FOUND
======================================================================

📊 Search Parameters:
   • Attendees: 3 people
   • Duration: 60 minutes
   • Location: Virtual
   • Window: Friday, March 15, 2024

🏆 Top 5 Recommended Times:

1. Fri 2024-03-15 10:00 – 11:00
   Score: [████████░░] 85.0/100
   ✅ Optimal time of day, Virtual (flexible)

2. Fri 2024-03-15 15:00 – 16:00
   Score: [███████░░░] 75.0/100
   ✅ Optimal time of day
   ⚠️  Friday (end of week)

3. Fri 2024-03-15 12:00 – 13:00
   Score: [██████░░░░] 60.0/100
   ⚠️  Overlaps lunch

======================================================================
```

## Advanced Usage

### Using the Python Module Directly

```python
from scheduler import create_meeting_with_dates, format_slot_datetime, parse_window_datetime

# Define your search window
window_start = "2024-03-15T09:00:00-05:00"
window_end = "2024-03-15T17:00:00-05:00"

# Define participants and their events
people_events = [
    {
        "id": "alice",
        "name": "Alice Johnson",
        "email": "alice@company.com",
        "timezone": "America/New_York",
        "events": [
            {
                "start": {"dateTime": "2024-03-15T10:00:00-05:00"},
                "end": {"dateTime": "2024-03-15T11:00:00-05:00"},
                "summary": "Team Standup"
            }
        ]
    }
]

# Find optimal slots
optimal_slots = create_meeting_with_dates(
    window_start_dt=window_start,
    window_end_dt=window_end,
    people_events=people_events,
    duration=60,
    location_type="virtual",
    top_k=5
)

# Display results
window_start_dt = parse_window_datetime(window_start)
for slot in optimal_slots:
    time_str = format_slot_datetime(slot.start, window_start_dt, 60)
    print(f"{time_str} - Score: {slot.score:.1f}")
```

## Troubleshooting

### "No calendar data loaded"
- Check that `calendars.json` exists and is valid JSON
- Verify file path with `--calendars` option

### "Error parsing dates"
- Use ISO 8601 format: `YYYY-MM-DDTHH:MM:SS-05:00`
- Include timezone offset or use `--timezone` flag

### "Google Calendar API libraries not installed"
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### "credentials.json not found"
- Follow Google Calendar API setup instructions above
- Download OAuth credentials from Google Cloud Console

## Files Overview

- `meeting_optimizer.py` - Main CLI tool for finding meeting times
- `google_calendar_helper.py` - Fetch calendars from Google Calendar API
- `scheduler.py` - Core scheduling algorithm (your existing file)
- `calendars.json` - Sample calendar data (or output from helper)
- `org_settings.json` - Organization preferences and scoring rules

## License

MIT

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.
