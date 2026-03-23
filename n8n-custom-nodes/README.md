# n8n Nodes for Convis

Custom n8n nodes for integrating with the Convis call automation platform.

## Nodes

### Convis Trigger

A webhook trigger node that receives events from Convis:

- **Call Completed** - Triggered when a call ends successfully
- **Call Failed** - Triggered when a call fails
- **Call No Answer** - Triggered when no one answers
- **Campaign Completed** - Triggered when a campaign finishes

#### Event Data Structure

When a call completes, the following data is sent:

```json
{
  "event": "call_completed",
  "timestamp": "2024-01-06T10:30:00Z",
  "user_id": "user123",
  "call": {
    "id": "CA1234567890",
    "status": "completed",
    "duration": 120,
    "direction": "outbound",
    "from_number": "+1234567890",
    "to_number": "+0987654321",
    "transcript": "Full call transcript...",
    "summary": "Summary of the call...",
    "sentiment": "positive",
    "sentiment_score": 0.85,
    "recording_url": "https://..."
  },
  "customer": {
    "name": "John Doe",
    "phone": "+0987654321",
    "email": "john@example.com"
  },
  "assistant": {
    "id": "assistant123",
    "name": "Sales Assistant"
  },
  "campaign": {
    "id": "campaign123",
    "name": "January Outreach"
  },
  "extracted_info": {
    "appointment_booked": true,
    "appointment_date": "2024-01-10"
  }
}
```

## Installation

### Option 1: Install from npm (when published)

```bash
npm install n8n-nodes-convis
```

### Option 2: Manual Installation

1. Build the package:
   ```bash
   cd n8n-custom-nodes
   npm install
   npm run build
   ```

2. Copy to n8n custom nodes directory:
   ```bash
   cp -r dist ~/.n8n/custom/
   ```

3. Restart n8n

## Configuration

### Setting up the Webhook

1. In n8n, create a new workflow
2. Add the "Convis Trigger" node
3. Select the event type you want to listen for
4. Copy the webhook URL from the node
5. In Convis, configure your assistant to use this webhook URL

### Filtering Options

- **Filter by Sentiment**: Only trigger for calls with specific sentiment (positive, negative, neutral)
- **Minimum Call Duration**: Only trigger for calls longer than specified duration

## Example Workflows

### Send Email After Positive Calls

1. Convis Trigger (Call Completed, Sentiment: Positive)
2. IF node (check if customer email exists)
3. Send Email node

### Create CRM Contact After Call

1. Convis Trigger (Call Completed)
2. HubSpot node (Create Contact)
3. Slack node (Notify team)

### Schedule Follow-up for Negative Sentiment

1. Convis Trigger (Call Completed, Sentiment: Negative)
2. Wait node (1 day)
3. Google Calendar node (Create reminder)

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Watch mode
npm run dev
```

## License

MIT
