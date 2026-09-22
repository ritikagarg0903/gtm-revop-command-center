"""Transactional lead state machine and durable action outbox.

An integration supplies scored records and uniquely identified events. CRM/email
adapters consume pending actions and acknowledge delivery; queuing is not sending.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import pandas as pd
from src.lifecycle import CADENCE, EVENT_POINTS
from src.nurture_campaigns import EMAIL_STEPS


class Workflow:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY, lead_id TEXT, old_stage TEXT, new_stage TEXT, reason TEXT, at TEXT);
            CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, lead_id TEXT, kind TEXT, payload TEXT, status TEXT DEFAULT 'pending', created_at TEXT);
        ''')

    def close(self):
        self.db.close()

    def _action(self, key, lead, kind, payload, now):
        self.db.execute('INSERT OR IGNORE INTO actions(id,lead_id,kind,payload,created_at) VALUES(?,?,?,?,?)',
                        (key, lead['prospect_id'], kind, json.dumps(payload), now.isoformat()))

    def _move(self, lead, stage, reason, now):
        old = lead['lifecycle_stage']
        if old == stage:
            return
        self.db.execute('INSERT INTO movements(lead_id,old_stage,new_stage,reason,at) VALUES(?,?,?,?,?)',
                        (lead['prospect_id'], old, stage, reason, now.isoformat()))
        change_id = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        lead['lifecycle_stage'] = stage
        self._action(f'movement:{change_id}', lead, 'crm_stage_update', {'stage': stage, 'reason': reason}, now)

    def _nurture(self, lead, now, reason):
        lead.update(status='nurture', nurture_entry_date=now.isoformat(), engagement_score=0,
                    nurture_touch_count=0, assigned_rep='', nurture_last_sent_date=None,
                    nurture_opens=0, nurture_clicks=0, nurture_replies=0, nurture_last_engagement=None, cadence_status='completed-no response' if lead['cadence_start_date'] else 'not started')
        self._move(lead, 'Nurture', reason, now)

    def run(self, records, reps, events=(), now=None):
        now = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
        now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
        with self.db:
            # Serialize workers before reading state; a duplicate event cannot race a transition.
            self.db.execute('UPDATE leads SET id=id WHERE 0')
            leads = {key: json.loads(value) for key, value in self.db.execute('SELECT id,payload FROM leads')}
            for row in records.to_dict('records'):
                key = str(row['prospect_id'])
                if not key or key == 'nan':
                    raise ValueError('prospect_id is required')
                for field in ('email_valid', 'domain_valid', 'is_duplicate'):
                    if type(row[field]) is not bool:
                        raise ValueError(field + ' must be a boolean')
                if not 0 <= float(row['total_score']) <= 100:
                    raise ValueError('total_score must be between 0 and 100')
                base = leads.setdefault(key, dict(prospect_id=key, status='active', lifecycle_stage='Lead',
                    nurture_entry_date=None, engagement_score=0, nurture_touch_count=0,
                    re_engagement_date=None, cadence_status='not started', cadence_step=0,
                    assigned_rep='', last_touch_date=None, response_date=None, cadence_start_date=None,
                    was_unassigned=False, next_action='', engagement_events='', blocked=False))
                # Only source-owned fields are updated; incoming snapshots cannot erase workflow history.
                for field in ('account_name', 'segment', 'territory', 'email_valid', 'domain_valid', 'is_duplicate', 'total_score'):
                    base[field] = row[field]
            for event in sorted(events, key=lambda e: e['occurred_at']):
                key = str(event['prospect_id'])
                at = pd.Timestamp(event['occurred_at'])
                if at.tzinfo is None:
                    at = at.tz_localize('UTC')
                if at > now or key not in leads:
                    continue
                if event['type'] not in {*EVENT_POINTS, 'opportunity_created', 'customer_won'}:
                    raise ValueError('Unsupported event type: ' + event['type'])
                inserted = self.db.execute('INSERT OR IGNORE INTO events(id,payload) VALUES(?,?)',
                                          (event['event_id'], json.dumps(event))).rowcount
                if not inserted:
                    continue
                lead = leads[key]
                valid = lead['email_valid'] and lead['domain_valid'] and not lead['is_duplicate']
                kind = event['type']
                if kind in EVENT_POINTS and valid:
                    if lead['status'] == 'nurture' and at >= pd.Timestamp(lead['nurture_entry_date']):
                        lead['engagement_score'] += EVENT_POINTS[kind]
                        counter = {'open': 'nurture_opens', 'click': 'nurture_clicks', 'reply': 'nurture_replies'}.get(kind)
                        if counter:
                            lead[counter] = lead.get(counter, 0) + 1
                        previous = lead.get('nurture_last_engagement')
                        if previous is None or at > pd.Timestamp(previous):
                            lead['nurture_last_engagement'] = at.isoformat()
                    if kind == 'reply' and lead['cadence_status'] == 'in progress' and at >= pd.Timestamp(lead['cadence_start_date']):
                        lead.update(response_date=at.isoformat(), cadence_status='sales-engaged', status='active')
                        self._move(lead, 'SQL', 'Lead replied during cadence', now)
                elif kind == 'opportunity_created' and valid and lead['lifecycle_stage'] != 'Customer':
                    lead.update(status='active', cadence_status='sales-engaged')
                    self._move(lead, 'Opportunity', 'CRM opportunity-created event', now)
                elif kind == 'customer_won' and valid:
                    lead.update(status='active', cadence_status='sales-engaged')
                    self._move(lead, 'Customer', 'CRM closed-won event', now)
            loads = {r.rep_name: int(r.current_load) for _, r in reps.iterrows()}
            for lead in leads.values():
                if lead['status'] == 'nurture':
                    lead['assigned_rep'] = ''
                if lead['assigned_rep'] in loads:
                    loads[lead['assigned_rep']] += 1
            for key, lead in sorted(leads.items()):
                valid = lead['email_valid'] and lead['domain_valid'] and not lead['is_duplicate']
                lead['blocked'] = not valid
                if not valid:
                    lead['next_action'] = 'Repair invalid data or merge duplicate'
                elif lead['lifecycle_stage'] in ('SQL', 'Opportunity', 'Customer'):
                    lead['next_action'] = 'Sales follow-up' if lead['lifecycle_stage'] == 'SQL' else 'Await CRM outcome'
                else:
                    if lead['lifecycle_stage'] == 'Lead':
                        if lead['total_score'] < 70:
                            self._nurture(lead, now, 'Qualification score below 70')
                        else:
                            self._move(lead, 'MQL', 'Qualification score reached 70', now)
                    if lead['lifecycle_stage'] == 'MQL' and not lead['assigned_rep']:
                        pool = [r for _, r in reps.iterrows() if r.available and
                                lead['territory'] in r.territories.split('|') and lead['segment'] in r.segments.split('|') and
                                loads[r.rep_name] < r.max_capacity]
                        lead['was_unassigned'] = True
                        if pool:
                            rep = min(pool, key=lambda r: (loads[r.rep_name] / r.max_capacity, r.rep_name))
                            loads[rep.rep_name] += 1
                            lead.update(assigned_rep=rep.rep_name, cadence_status='in progress', cadence_start_date=now.isoformat())
                            self._action('owner:' + key, lead, 'crm_owner_update', {'owner': rep.rep_name}, now)
                        else:
                            lead['next_action'] = 'Assign an available territory/segment owner'
                    if lead['status'] == 'nurture':
                        age = (now - pd.Timestamp(lead['nurture_entry_date'])).days
                        if lead['engagement_score'] >= 20:
                            lead.update(status='re-engaged', re_engagement_date=now.isoformat(), next_action='Sales handoff')
                            self._move(lead, 'SQL', 'Nurture engagement reached 20', now)
                        elif age >= 90 and lead['engagement_score'] == 0:
                            lead.update(status='dormant', next_action='Retained for future reactivation')
                            self._move(lead, 'Dormant', '90 days without engagement', now)
                        else:
                            step = lead['nurture_touch_count']
                            lead['next_action'] = 'Monitor engagement' if step >= 4 else 'Deliver next nurture email'
                            if step < 4 and age >= (0, 7, 14, 21)[step]:
                                self._action(f'nurture:{key}:{lead["nurture_entry_date"]}:{step}', lead, 'nurture_email', {'step': step + 1, 'campaign': f"{lead['segment']} · Educational nurture",
                                     'email_type': EMAIL_STEPS[step][1], 'theme': EMAIL_STEPS[step][2],
                                     'call_to_action': EMAIL_STEPS[step][3]}, now)
                    if lead['cadence_status'] == 'in progress' and lead['lifecycle_stage'] == 'MQL':
                        step = lead['cadence_step']
                        if step < len(CADENCE):
                            day, action = CADENCE[step]
                            due = pd.Timestamp(lead['cadence_start_date']) + pd.offsets.BDay(day)
                            lead['next_action'] = action + ' due ' + due.date().isoformat()
                            if now >= due:
                                self._action(f'cadence:{key}:{step}', lead, 'cadence_task', {'step': step + 1, 'action': action}, now)
                        elif now >= pd.Timestamp(lead['last_touch_date']) + pd.Timedelta(days=1):
                            self._nurture(lead, now, 'Cadence completed without response')
                            lead['next_action'] = 'Deliver first nurture email'
                if valid and lead['lifecycle_stage'] == 'SQL' and not lead['assigned_rep']:
                    pool = [r for _, r in reps.iterrows() if r.available and
                            lead['territory'] in r.territories.split('|') and lead['segment'] in r.segments.split('|') and
                            loads[r.rep_name] < r.max_capacity]
                    if pool:
                        rep = min(pool, key=lambda r: (loads[r.rep_name] / r.max_capacity, r.rep_name))
                        loads[rep.rep_name] += 1
                        lead['assigned_rep'] = rep.rep_name
                        self._action('owner:' + key, lead, 'crm_owner_update', {'owner': rep.rep_name}, now)
                    else:
                        lead['next_action'] = 'Assign an available owner for recovered SQL'
                # Stop pending outreach immediately on reply, promotion, dormancy or data failure.
                if lead['blocked'] or lead['lifecycle_stage'] in ('SQL', 'Opportunity', 'Customer', 'Dormant'):
                    self.db.execute("UPDATE actions SET status='cancelled' WHERE lead_id=? AND status='pending' AND kind IN ('nurture_email','cadence_task')", (key,))
                self.db.execute('INSERT OR REPLACE INTO leads VALUES(?,?)', (key, json.dumps(lead, default=str)))
        return self.records()

    def acknowledge(self, action_id, now=None):
        """Integration callback after successful delivery, never after mere scheduling."""
        now = pd.Timestamp(now or pd.Timestamp.now(tz='UTC')).isoformat()
        with self.db:
            self.db.execute('UPDATE leads SET id=id WHERE 0')
            row = self.db.execute("SELECT lead_id,kind,payload FROM actions WHERE id=? AND status='pending'", (action_id,)).fetchone()
            if row is None:
                return False
            key, kind, payload = row
            lead = json.loads(self.db.execute('SELECT payload FROM leads WHERE id=?', (key,)).fetchone()[0])
            if kind == 'nurture_email':
                lead['nurture_touch_count'] += 1
                lead['nurture_last_sent_date'] = now
            elif kind == 'cadence_task':
                lead['cadence_step'] += 1
            if kind in ('nurture_email', 'cadence_task'):
                lead['last_touch_date'] = now
            self.db.execute("UPDATE actions SET status='delivered' WHERE id=?", (action_id,))
            self.db.execute('UPDATE leads SET payload=? WHERE id=?', (json.dumps(lead), key))
            return True

    def records(self):
        rows = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM leads ORDER BY id')]
        return pd.DataFrame(rows)

    def movements(self):
        return pd.read_sql_query('SELECT lead_id,old_stage,new_stage,reason,at FROM movements ORDER BY id DESC', self.db)

    def actions(self):
        return pd.read_sql_query('SELECT * FROM actions ORDER BY created_at,id', self.db)
