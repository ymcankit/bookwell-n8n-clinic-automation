"""Step 7: weekly summary email to the practice manager (Mondays 8:00 AM clinic time).
usage: python3 build_summary.py <sheetsCredId> <gmailCredId> <errorWorkflowId> [--test-link]"""
import json, sys
from common import config_node, sticky, settings, RETRY, doc_ref, CLINIC

SPREADSHEET_ID = CLINIC["spreadsheetId"]
SHEETS = {"googleSheetsOAuth2Api": {"id": sys.argv[1], "name": "Google Sheets account"}}
GMAIL = {"gmailOAuth2": {"id": sys.argv[2], "name": "Gmail account"}}
DOC = doc_ref()

SUMMARY = r"""// Build the weekly practice-manager summary from the Patients + Waitlist sheets
const C = $('Clinic Config').first().json;
const ZONE = C.clinicTimezone;
const now = DateTime.now().setZone(ZONE);
const weekAgo = now.minus({ days: 7 });
const weekAhead = now.plus({ days: 7 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const parseStart = s => {
  const m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})/);
  return m ? DateTime.fromObject({ year: +m[1], month: +m[2], day: +m[3], hour: +m[4], minute: +m[5] }, { zone: ZONE }) : null;
};

const patients = $('Read Patients').all().map(i => i.json).filter(r => r['Booking ID']);
const waitlist = $('Read Waitlist').all().map(i => i.json).filter(r => r.waitlistId);
const managerEmail = C.managerEmail || $('Get Manager Inbox Address').first().json.emailAddress;

const isCancelled = r => String(r['Status']).toLowerCase().startsWith('cancelled');
const thisWeek = patients.filter(r => { const t = DateTime.fromISO(String(r['Submitted At'])); return t.isValid && t >= weekAgo; });
const count = (rows, key) => rows.reduce((m, r) => (m[r[key] || '—'] = (m[r[key] || '—'] || 0) + 1, m), {});

const kpi = {
  requests: thisWeek.length,
  questions: thisWeek.filter(r => r['Question']).length,
  escalated: thisWeek.filter(r => r['Needs Staff'] === 'YES').length,
  symptom: thisWeek.filter(r => ['health', 'urgent', 'symptom', 'keyword-review'].includes(r['AI Category'])).length,
  slotIssues: thisWeek.filter(r => r['Slot Issue']).length,
  confFailed: thisWeek.filter(r => String(r['Confirmation Sent At']).startsWith('FAILED')).length,
  cancelled: thisWeek.filter(isCancelled).length,
  remindersSent: patients.filter(r => { const t = DateTime.fromISO(String(r['Reminder Sent At'])); return t.isValid && t >= weekAgo; }).length,
  waiting: waitlist.filter(w => String(w.status).toLowerCase() === 'waiting').length,
  offered: waitlist.filter(w => { const t = DateTime.fromISO(String(w.notifiedAt)); return t.isValid && t >= weekAgo; }).length,
};

const upcoming = patients
  .map(r => ({ r, start: parseStart(r['Appointment Start']) }))
  .filter(x => x.start && x.start >= now && x.start <= weekAhead && !isCancelled(x.r))
  .sort((a, b) => a.start - b.start);
const openFollowUps = patients.filter(r => r['Needs Staff'] === 'YES' && !isCancelled(r) && (parseStart(r['Appointment Start']) || now) >= now.startOf('day'));

// ---- HTML (table-based so it renders in every mail client) ----
const tile = (label, value, warn) => `<td style="padding:6px"><div style="border:1px solid #e3e7ec;border-radius:8px;padding:12px 14px;min-width:110px">
  <div style="font-size:12px;color:#5b6472">${label}</div><div style="font-size:24px;font-weight:700;color:${warn && value ? '#b42318' : '#1f2933'}">${value}</div></div></td>`;
const breakdown = obj => Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${esc(k)}: <b>${v}</b>`).join(' · ') || '—';
const th = s => `<th style="text-align:left;padding:6px 10px;border-bottom:2px solid #e3e7ec;font-size:12px;color:#5b6472">${s}</th>`;
const td = s => `<td style="padding:6px 10px;border-bottom:1px solid #f0f2f5;font-size:13px">${s}</td>`;

const upcomingRows = upcoming.map(({ r, start }) => `<tr>${td(esc(start.toFormat('ccc d LLL, h:mm a')))}${td(esc(r['Full Name']))}${td(esc(r['Reason']))}${td(esc(r['Status']))}${td(r['Needs Staff'] === 'YES' ? '⚠️' : '')}</tr>`).join('');
const followRows = openFollowUps.map(r => `<tr>${td(esc(r['Booking ID']))}${td(esc(r['Full Name']))}${td(esc([r['AI Category'] !== 'faq' && r['AI Category'] !== 'none' ? r['AI Category'] : '', r['Slot Issue']].filter(Boolean).join('; ') || 'flagged'))}</tr>`).join('');

const range = `${weekAgo.toFormat('LLL d')} – ${now.toFormat('LLL d, yyyy')}`;
const html = `<div style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:auto;color:#1f2933;line-height:1.45">
  <h2 style="color:#1d6f5f;margin-bottom:0">${esc(C.clinicName)} · weekly summary</h2>
  <p style="margin-top:4px;color:#5b6472">${range} · generated ${now.toFormat("ccc d LLL, h:mm a")} clinic time</p>
  <table><tr>${tile('New requests', kpi.requests)}${tile('Needs follow-up', kpi.escalated, true)}${tile('Cancelled (this week\'s requests)', kpi.cancelled)}${tile('On waitlist', kpi.waiting)}</tr>
         <tr>${tile('Questions asked', kpi.questions)}${tile('Health-related', kpi.symptom, true)}${tile('Reminders sent', kpi.remindersSent)}${tile('Waitlist offers', kpi.offered)}</tr></table>
  <p><b>By visit type:</b> ${breakdown(count(thisWeek, 'Reason'))}<br><b>By time window:</b> ${breakdown(count(thisWeek, 'Preferred Time'))}</p>
  ${kpi.slotIssues || kpi.confFailed ? `<p style="background:#fff4d6;border-left:4px solid #e0a800;padding:8px 12px">${kpi.slotIssues} request(s) outside clinic hours · ${kpi.confFailed} confirmation email(s) failed</p>` : ''}
  <h3 style="margin:22px 0 6px">Next 7 days (${upcoming.length})</h3>
  ${upcoming.length ? `<table style="border-collapse:collapse;width:100%"><tr>${th('When')}${th('Patient')}${th('Visit')}${th('Status')}${th('')}</tr>${upcomingRows}</table>` : '<p style="color:#5b6472">No appointments in the next 7 days.</p>'}
  <h3 style="margin:22px 0 6px">Open follow-ups (${openFollowUps.length})</h3>
  ${openFollowUps.length ? `<table style="border-collapse:collapse;width:100%"><tr>${th('Booking')}${th('Patient')}${th('Why')}</tr>${followRows}</table>` : '<p style="color:#5b6472">Nothing waiting on staff. 🎉</p>'}
  <p style="margin-top:22px"><a href="https://docs.google.com/spreadsheets/d/${esc(C.spreadsheetId)}/edit">Open the Patients sheet</a></p>
  <p style="font-size:11px;color:#9aa3ad">BookWell is a fictional clinic used in a portfolio demo. All data is made up.</p></div>`;

return [{ json: { managerEmail, subject: `${C.clinicName} weekly summary – ${range}`, html, kpi } }];"""

nodes = [
  sticky("n1", "## Weekly practice-manager summary\nMondays 8 AM clinic time. Reads both sheets and emails KPI tiles, a visit-type breakdown, the next 7 days and open follow-ups.\nRecipient: **Clinic Config → managerEmail** (blank = the signed-in Gmail inbox).", -60, -60, 1400, 140, 5),
  {"id": "t1", "name": "Every Monday 8 AM", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 200],
   "parameters": {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 8, "triggerAtMinute": 0}]}}},
  {"id": "t2", "name": "Run Now (test link)", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 420],
   "webhookId": "b00c11a0-5a11-4a11-9e11-b00c11a0f005", "disabled": "--test-link" not in sys.argv,
   "parameters": {"httpMethod": "GET", "path": "bookwell-weekly-summary-run", "responseMode": "onReceived", "options": {}}},
  config_node(220, 300),
  {"id": "r1", "name": "Read Patients", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.7, "position": [440, 300], "credentials": SHEETS, **RETRY,
   "executeOnce": True, "alwaysOutputData": True,
   "parameters": {"operation": "read", "documentId": DOC, "sheetName": {"__rl": True, "mode": "name", "value": "Patients"}, "options": {}}},
  {"id": "r2", "name": "Read Waitlist", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.7, "position": [660, 300], "credentials": SHEETS, **RETRY,
   "executeOnce": True, "alwaysOutputData": True,
   "parameters": {"operation": "read", "documentId": DOC, "sheetName": {"__rl": True, "mode": "name", "value": "Waitlist"}, "options": {}}},
  {"id": "h1", "name": "Get Manager Inbox Address", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [880, 300], "credentials": GMAIL, **RETRY,
   "executeOnce": True,
   "parameters": {"method": "GET", "url": "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                  "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2", "options": {}}},
  {"id": "c1", "name": "Build Weekly Summary", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, 300],
   "parameters": {"jsCode": SUMMARY}},
  {"id": "g1", "name": "Email Practice Manager (Gmail)", "type": "n8n-nodes-base.gmail", "typeVersion": 2.1, "position": [1320, 300], "credentials": GMAIL, **RETRY,
   "parameters": {"resource": "message", "operation": "send", "sendTo": "={{ $json.managerEmail }}",
                  "subject": "={{ $json.subject }}", "emailType": "html", "message": "={{ $json.html }}",
                  "options": {"appendAttribution": False, "senderName": "={{ $('Clinic Config').first().json.clinicName + ' – Reports' }}"}}},
]
order = ["Clinic Config", "Read Patients", "Read Waitlist", "Get Manager Inbox Address", "Build Weekly Summary", "Email Practice Manager (Gmail)"]
conn = {"Every Monday 8 AM": {"main": [[{"node": "Clinic Config", "type": "main", "index": 0}]]},
        "Run Now (test link)": {"main": [[{"node": "Clinic Config", "type": "main", "index": 0}]]}}
for a, b in zip(order, order[1:]):
    conn[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}

json.dump({"name": "BookWell – Weekly Manager Summary", "nodes": nodes, "connections": conn,
           "settings": settings(sys.argv[3])},
          sys.stdout, indent=2, ensure_ascii=False)
