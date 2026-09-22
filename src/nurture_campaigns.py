"""Marketing-owned nurture campaign tracking, derived from persisted workflow state."""
import pandas as pd

EMAIL_STEPS = [
    (0, 'Educational guide', 'A practical guide to improving your workflow', 'Read the guide'),
    (7, 'Customer use case', 'How a similar team approached the problem', 'Explore the use case'),
    (14, 'Checklist', 'A checklist to assess your current process', 'Download the checklist'),
    (21, 'Resource roundup', 'Useful resources for your next steps', 'Explore resources'),
]


def campaign_records(leads, sender='Not configured'):
    columns = ['prospect_id', 'account_name', 'campaign_name', 'campaign_status', 'sender_email',
               'email_type', 'email_theme', 'call_to_action', 'sequence_progress', 'enrolled_on',
               'last_email_sent', 'next_email_due', 'opens', 'clicks', 'replies', 'engagement_score', 'last_engagement']
    rows = []
    for lead in leads.to_dict('records'):
        if lead.get('status') != 'nurture' or not lead.get('nurture_entry_date'):
            continue
        sent = int(lead['nurture_touch_count'])
        paused = bool(lead.get('blocked'))
        offset, kind, theme, cta = EMAIL_STEPS[min(sent, len(EMAIL_STEPS) - 1)]
        rows.append(dict(prospect_id=lead['prospect_id'], account_name=lead['account_name'],
            campaign_name=f"{lead['segment']} · Educational nurture", campaign_status='Paused — data repair' if paused else
            ('Sequence complete — monitoring engagement' if sent >= 4 else 'Enrolled'),
            sender_email=sender or 'Not configured', email_type=kind if sent < 4 else 'Sequence complete',
            email_theme=theme if sent < 4 else '—', call_to_action=cta if sent < 4 else '—',
            sequence_progress=f'{sent} / 4 sent', enrolled_on=lead['nurture_entry_date'],
            last_email_sent=lead.get('nurture_last_sent_date'),
            next_email_due=(pd.Timestamp(lead['nurture_entry_date']) + pd.Timedelta(days=offset)).isoformat() if sent < 4 and not paused else None,
            opens=lead.get('nurture_opens'), clicks=lead.get('nurture_clicks'), replies=lead.get('nurture_replies'),
            engagement_score=lead['engagement_score'], last_engagement=lead.get('nurture_last_engagement')))
    result = pd.DataFrame(rows, columns=columns)
    for column in ['enrolled_on', 'last_email_sent', 'next_email_due', 'last_engagement']:
        result[column] = pd.to_datetime(result[column], utc=True)
    return result
