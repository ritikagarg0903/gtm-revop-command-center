"""Deterministic presentation-only sample history. Never writes to workflow state or sends messages."""
import hashlib
import pandas as pd
from src.lifecycle import CADENCE
from src.nurture_campaigns import campaign_records


def demo_activity(leads, now=None):
    now = pd.Timestamp(now or pd.Timestamp.now(tz='UTC')).normalize()
    result = leads.astype(object).copy()
    history = []
    rows = []
    for lead in result.to_dict('records'):
        if lead['blocked']:
            continue
        seed = int(hashlib.sha256(lead['prospect_id'].encode()).hexdigest()[:8], 16)
        bucket = seed % 12
        key = result.index[result.prospect_id.eq(lead['prospect_id'])][0]
        if bucket < 6:
            sent = bucket if bucket < 4 else 4
            entry = now - pd.Timedelta(days=(0, 4, 10, 17, 35, 95)[bucket])
            campaign_state = ['Scheduled', 'Active', 'Active', 'Active', 'Completed', 'Dormant'][bucket]
            if bucket == 4 and (seed // 12) % 5 == 0:
                campaign_state = 'Unsubscribed'
            elif bucket == 2 and (seed // 12) % 7 == 0:
                campaign_state = 'Bounced'
            elif bucket == 4 and (seed // 12) % 3 == 0:
                campaign_state = 'Recovered to SQL'
            lead.update(status='nurture', nurture_entry_date=entry.isoformat(), assigned_rep='',
                        nurture_touch_count=sent, engagement_score=0, nurture_opens=0, nurture_clicks=0,
                        nurture_replies=0, nurture_last_sent_date=None, nurture_last_engagement=None)
            delivered_count = opened_count = clicked_count = replied_count = 0
            for step in range(sent):
                at = entry + pd.Timedelta(days=(0, 7, 14, 21)[step])
                delivered = campaign_state != 'Bounced'
                opened = delivered and bucket != 5 and (seed + step * 13) % 100 < 57
                clicked = opened and (seed + step * 7) % 100 < 23
                replied = clicked and (seed + step) % 100 < 9
                if campaign_state == 'Recovered to SQL' and step == sent - 1:
                    opened = clicked = replied = True
                history.append(dict(prospect_id=lead['prospect_id'], segment=lead['segment'],
                    email_id=f"demo:{lead['prospect_id']}:{step}", sent_at=at,
                    delivered=delivered, opened=opened, clicked=clicked, replied=replied))
                delivered_count += int(delivered); opened_count += int(opened)
                clicked_count += int(clicked); replied_count += int(replied)
                lead['nurture_last_sent_date'] = at.isoformat()
                if opened:
                    lead['nurture_last_engagement'] = at.isoformat()
            lead.update(nurture_opens=opened_count, nurture_clicks=clicked_count, nurture_replies=replied_count,
                        engagement_score=opened_count + clicked_count * 3 + replied_count * 10)
            if campaign_state == 'Recovered to SQL':
                lead['engagement_score'] = max(20, lead['engagement_score'])
            campaign = campaign_records(pd.DataFrame([lead]), 'marketing@company.example').iloc[0].to_dict()
            campaign.update(campaign_status=campaign_state, emails_sent=sent, emails_delivered=delivered_count,
                            opens=opened_count, clicks=clicked_count, replies=replied_count)
            for field, count in [('open_rate', opened_count), ('click_rate', clicked_count), ('reply_rate', replied_count)]:
                campaign[field] = count / delivered_count * 100 if delivered_count else None
            if campaign_state in ('Completed', 'Dormant', 'Unsubscribed', 'Bounced', 'Recovered to SQL'):
                campaign.update(next_email_due=pd.NaT, email_type='—', email_theme='—', call_to_action='—')
            rows.append(campaign)
            lead.update(lifecycle_stage='SQL' if campaign_state == 'Recovered to SQL' else 'Dormant' if campaign_state == 'Dormant' else 'Nurture',
                        status='re-engaged' if campaign_state == 'Recovered to SQL' else 'dormant' if campaign_state == 'Dormant' else 'nurture',
                        next_action='Sales handoff' if campaign_state == 'Recovered to SQL' else 'Marketing campaign: ' + campaign_state)
            if campaign_state == 'Recovered to SQL':
                lead['re_engagement_date'] = (entry + pd.Timedelta(days=22)).isoformat()
        else:
            step = min(bucket - 6, 4)
            start = now - pd.offsets.BDay((0, 3, 6, 8, 12, 15)[bucket - 6])
            stage = ['MQL', 'MQL', 'MQL', 'SQL', 'Opportunity', 'Customer'][bucket - 6]
            lead.update(lifecycle_stage=stage, status='active', cadence_step=step,
                        nurture_entry_date=None, re_engagement_date=None, nurture_touch_count=0,
                        cadence_start_date=start.isoformat(), cadence_status='in progress' if stage == 'MQL' else 'sales-engaged',
                        last_touch_date=(start + pd.offsets.BDay(CADENCE[max(0, step - 1)][0])).isoformat() if step else None,
                        response_date=(start + pd.offsets.BDay(5)).isoformat() if stage != 'MQL' else None,
                        next_action=CADENCE[step][1] if stage == 'MQL' else {'SQL': 'Discovery conversation', 'Opportunity': 'Confirm proposal and next meeting', 'Customer': 'Customer onboarding'}[stage])
        for field, value in lead.items():
            if field not in result:
                result[field] = None
            result.at[key, field] = value
    campaigns = pd.DataFrame(rows)
    events = pd.DataFrame(history, columns=['prospect_id', 'segment', 'email_id', 'sent_at', 'delivered', 'opened', 'clicked', 'replied'])
    return result.infer_objects(), campaigns, events


def email_metrics(events):
    delivered = int(events.delivered.sum())
    sent = len(events)
    return {'sent': sent, 'delivered': delivered,
            'delivery_rate': 100 * delivered / sent if sent else None,
            **{name + '_rate': 100 * events[column].sum() / delivered if delivered else None
               for name, column in [('open', 'opened'), ('click', 'clicked'), ('reply', 'replied')]}}
