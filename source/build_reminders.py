"""BookWell – Reminders & Waitlist (hourly): 24h reminders, waitlist offers on cancellation, calendar cleanup.
usage: python3 build_reminders.py <sheetsCredId> <gmailCredId> <calendarCredId> <errorWorkflowId> [--test-link]"""
import sys
from common import *

SHEETS, GMAIL, GCAL = creds("googleSheetsOAuth2Api", sys.argv[1]), creds("gmailOAuth2", sys.argv[2]), creds("googleCalendarOAuth2Api", sys.argv[3])
ERROR_WF = sys.argv[4]
TEST_LINK_ENABLED = "--test-link" in sys.argv
PRIMARY = {"__rl": True, "mode": "list", "value": "primary", "cachedResultName": "Primary calendar"}

FIND = r"""// Scan the Patients sheet and decide what needs doing this hour
const C = $('Clinic Config').first().json;
const ZONE = C.clinicTimezone;
const now = DateTime.now().setZone(ZONE);
const parseStart = s => {   // accepts "2026-11-20 09:00", "2026-11-20 9:00:00", "2026-11-20T09:00:00-05:00"
  const str = String(s || '');
  const iso = DateTime.fromISO(str, { setZone: true });
  if (iso.isValid && /[T ]\d/.test(str) && /[+-]\d\d:\d\d$|Z$/.test(str)) return iso.setZone(ZONE);
  const m = str.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})/);
  return m ? DateTime.fromObject({ year: +m[1], month: +m[2], day: +m[3], hour: +m[4], minute: +m[5] }, { zone: ZONE }) : null;
};
const isNewCancellation = s => /^\s*cancel+ed\s*[.!]?\s*$/i.test(s);       // "Cancelled", "canceled", "CANCELLED."
const isAnyCancelled = s => /^\s*cancel+ed\b/i.test(s);                    // also matches processed "Cancelled – offered to …"
const unsent = v => !v || String(v).startsWith('FAILED');                  // failed sends are retried next hour

const out = [];
for (const { json: r } of $input.all()) {
  if (!r['Booking ID']) continue;
  const status = String(r['Status'] || '');
  const start = parseStart(r['Appointment Start']);
  const hoursAway = start ? start.diff(now, 'hours').hours : null;
  const base = {
    bookingId: r['Booking ID'], fullName: r['Full Name'], email: r['Email'], reason: r['Reason'],
    preferredTime: r['Preferred Time'], calendarEventId: r['Calendar Event ID'] || '', slotIssue: r['Slot Issue'] || '',
    startText: start ? start.toFormat("cccc, LLLL d") + ` (${r['Preferred Time'] || ''} window)` : r['Preferred Date'],
  };
  // 1) Reminder: active booking within 24h, no unresolved slot problem, not yet reminded
  if (/^\s*(tentative|confirmed)\s*$/i.test(status) && !r['Slot Issue'] && unsent(r['Reminder Sent At'])
      && hoursAway !== null && hoursAway > 0 && hoursAway <= 24) {
    out.push({ json: { kind: 'reminder', ...base, confirmed: /confirmed/i.test(status) } });
  }
  // 2) New cancellation typed by staff
  if (isNewCancellation(status)) out.push({ json: { kind: 'cancellation', ...base, slotInFuture: hoursAway !== null && hoursAway > 0 } });
  // 3) Calendar cleanup for any cancelled future booking (idempotent: the event title is checked before editing)
  if (isAnyCancelled(status) && base.calendarEventId && hoursAway !== null && hoursAway > 0) out.push({ json: { kind: 'calendarCleanup', ...base } });
}
return out;"""

COMPOSE_REMINDER = ESC_JS + r"""
const C = $('Clinic Config').first().json;
return $input.all().map(({ json: b }) => {
  const first = (b.fullName || '').split(' ')[0] || 'there';
  const statusLine = b.confirmed ? 'Your appointment is confirmed for:' : 'Your requested appointment is coming up (our team will confirm the exact time if they haven\'t already):';
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:auto;color:#1f2933;line-height:1.5">
  <h2 style="color:#1d6f5f;margin-bottom:4px">${esc(C.clinicName)}</h2>
  <p>Hi ${esc(first)},</p><p>${statusLine}</p>
  <p style="font-size:18px;font-weight:600;margin:12px 0">${esc(b.reason)} · ${esc(b.startText)}</p>
  <p>${esc(C.address)}<br>${esc(C.visitNotes)}${b.reason === 'New patient visit' ? ' New patients: please arrive 15 minutes early to complete forms.' : ''}</p>
  <p>Can't make it? Reply to this email or call ${esc(C.phone)} so we can offer the slot to someone on our waitlist.</p>
  <p style="font-size:12px;color:#5b6472">Booking ID ${esc(b.bookingId)} · For a medical emergency, call 911 or your local emergency number.</p>
  <p style="font-size:11px;color:#9aa3ad">${esc(C.clinicName)} is a fictional clinic used in a portfolio demo.</p></div>`;
  return { json: { ...b, emailSubject: `Reminder: your ${C.clinicName} appointment – ${b.startText}`, emailHtml: html } };
});"""

REMINDER_ROW = r"""const composed = $('Compose Reminder').all();
return $input.all().map((item, i) => ({ json: {
  'Booking ID': composed[i].json.bookingId,
  'Reminder Sent At': item.json.id ? new Date().toISOString() : 'FAILED: ' + (item.json.error?.message || item.json.error || 'unknown'),
}}));"""

MATCH = r"""// Pair each cancelled slot with the next person waiting (same time of day first, then longest wait)
const cancellations = $('New Cancellation?').all(0).map(i => i.json);
const waiting = $input.all().map(i => i.json)
  .filter(w => w.waitlistId && /^\s*waiting\s*$/i.test(String(w.status || '')))
  .sort((a, b) => String(a.addedAt).localeCompare(String(b.addedAt)));
const used = new Set();
return cancellations.map(c => {
  let pick = null;
  if (c.slotInFuture && !c.slotIssue) {        // never offer a slot that was outside clinic hours
    const pool = waiting.filter(w => !used.has(w.waitlistId));
    pick = pool.find(w => w.preferredTime === c.preferredTime) || pool[0] || null;
    if (pick) used.add(pick.waitlistId);
  }
  return { json: { ...c, hasMatch: !!pick,
    newStatus: !c.slotInFuture ? 'Cancelled – slot already passed' : c.slotIssue ? 'Cancelled – not offered (slot issue)' : pick ? `Cancelled – slot offered to ${pick.waitlistId}` : 'Cancelled – waitlist empty',
    waitlistId: pick?.waitlistId || '', waitlistName: pick?.fullName || '', waitlistEmail: pick?.email || '' } };
});"""

COMPOSE_OFFER = ESC_JS + r"""
const C = $('Clinic Config').first().json;
return $input.all().map(({ json: c }) => {
  const first = (c.waitlistName || '').split(' ')[0] || 'there';
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:auto;color:#1f2933;line-height:1.5">
  <h2 style="color:#1d6f5f;margin-bottom:4px">${esc(C.clinicName)}</h2>
  <p>Hi ${esc(first)},</p><p>Good news: an appointment opened up and you're next on our waitlist:</p>
  <p style="font-size:18px;font-weight:600;margin:12px 0">${esc(c.startText)}</p>
  <p>Want it? <strong>Reply to this email</strong> or call ${esc(C.phone)}. Our front desk will confirm the exact time with you.</p>
  <p style="font-size:12px;color:#5b6472">Waitlist ref ${esc(c.waitlistId)} · ${esc(C.address)}</p>
  <p style="font-size:11px;color:#9aa3ad">${esc(C.clinicName)} is a fictional clinic used in a portfolio demo.</p></div>`;
  return { json: { ...c, emailSubject: `An appointment opened up – ${c.startText}`, emailHtml: html } };
});"""

OFFER_RESULT = r"""// Only record an offer once Gmail confirms it was sent; otherwise the row stays "Cancelled" and is retried next hour
const composed = $('Compose Waitlist Offer').all();
return $input.all().map((item, i) => {
  const { emailHtml, emailSubject, ...c } = composed[i].json;
  return { json: { ...c, offerSent: !!item.json.id, offerError: item.json.id ? '' : (item.json.error?.message || item.json.error || 'unknown') } };
});"""

WAITLIST_ROW = r"""return $input.all().filter(i => i.json.offerSent).map(({ json: c }) => ({ json: {
  waitlistId: c.waitlistId, status: `Offered ${c.bookingId}`, notifiedAt: new Date().toISOString() } }));"""

PATIENT_ROW = r"""// Fed by two paths: sent offers (only if the email went out) and cancellations with nobody to offer to
return $input.all().filter(i => i.json.offerSent !== false).map(({ json: c }) => ({ json: { 'Booking ID': c.bookingId, 'Status': c.newStatus } }));"""

PICK_EVENTS = r"""// Keep only events that still exist and aren't already marked cancelled
const wanted = $('New Cancellation?').all(1).map(i => i.json);
const out = [];
$input.all().forEach((item, i) => {
  const ev = item.json, b = wanted[i] || {};
  if (!ev || ev.error || !ev.id) return;                          // event deleted by hand, or lookup failed
  if (String(ev.summary || '').startsWith('[CANCELLED')) return;   // already done on an earlier run
  const rest = String(ev.summary || `${b.reason} – ${b.fullName}`).replace(/^\[[^\]]*\]\s*/, '');
  out.push({ json: { calendarEventId: ev.id, newSummary: `[CANCELLED] ${rest}`,
    newDescription: `CANCELLED ${$now.toFormat('yyyy-MM-dd')}\n\n${ev.description || ''}` } });
});
return out;"""


def sheet_read(nid, name, tabname, x, y):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.7, "position": [x, y], "credentials": SHEETS, **RETRY,
            "executeOnce": True, "alwaysOutputData": True,
            "parameters": {"operation": "read", "documentId": doc_ref(), "sheetName": tab(tabname), "options": {}}}


def sheet_update(nid, name, tabname, match, x, y):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.7, "position": [x, y], "credentials": SHEETS, **RETRY,
            "parameters": {"operation": "update", "documentId": doc_ref(), "sheetName": tab(tabname),
                           "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [match], "schema": []},
                           "options": {"cellFormat": "RAW"}}}


def gmail(nid, name, to_expr, x, y):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.gmail", "typeVersion": 2.1, "position": [x, y], "credentials": GMAIL, **RETRY,
            "onError": "continueRegularOutput",
            "parameters": {"resource": "message", "operation": "send", "sendTo": to_expr, "subject": "={{ $json.emailSubject }}",
                           "emailType": "html", "message": "={{ $json.emailHtml }}",
                           "options": {"appendAttribution": False, "senderName": "={{ $('Clinic Config').first().json.clinicName }}"}}}


nodes = [
    sticky("n1", "## Hourly scan\nReads the **Patients** sheet once an hour and sorts rows into three jobs: **reminders**, **new cancellations**, **calendar cleanup**.\nState lives in the sheet (*Reminder Sent At*, *Status*), so a rerun never double-sends. Failed sends are retried next hour.", -60, -40, 1180, 160, 5),
    sticky("n2", "## 24-hour reminder\nOnly for Tentative/Confirmed bookings with no slot problem.", 1180, -120, 1000, 100, 4),
    sticky("n3", "## Cancellation → waitlist\nStaff type **Cancelled** (or *Canceled*) in Status. The next *Waiting* person (same morning/afternoon first, then longest wait) gets an offer email.\nStatuses are written **only after Gmail confirms the send**.", 1180, 380, 1700, 140, 6),
    sticky("n4", "## Calendar cleanup\nRenames the event **[CANCELLED]**, greys it out and marks it free. Checks the title first, so it is safe to repeat.", 1180, 1000, 900, 120, 7),
    {"id": "t1", "name": "Every Hour", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 200],
     "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}},
    {"id": "t2", "name": "Run Now (test link)", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 420], "disabled": not TEST_LINK_ENABLED,
     "webhookId": "b00c11a0-7e3d-4a11-9e11-b00c11a0f004",
     "parameters": {"httpMethod": "GET", "path": "bookwell-reminders-run", "responseMode": "onReceived", "options": {}}},
    config_node(220, 300),
    sheet_read("r1", "Read Patients", "Patients", 440, 300),
    code("f1", "Find Due Work", FIND, 660, 300),
    if_node("i1", "Is Reminder?", "={{ $json.kind }}", "eq", 880, 300, "reminder"),
    code("c1", "Compose Reminder", COMPOSE_REMINDER, 1240, 40),
    gmail("g1", "Send Reminder (Gmail)", "={{ $json.email }}", 1460, 40),
    code("m1", "Reminder Row", REMINDER_ROW, 1680, 40),
    sheet_update("u1", "Mark Reminder Sent", "Patients", "Booking ID", 1900, 40),
    if_node("i3", "New Cancellation?", "={{ $json.kind }}", "eq", 1000, 620, "cancellation"),
    sheet_read("r2", "Read Waitlist", "Waitlist", 1240, 580),
    code("m2", "Match Waitlist", MATCH, 1460, 580),
    if_node("i2", "Someone Waiting?", "={{ $json.hasMatch }}", "true", 1680, 580),
    code("c2", "Compose Waitlist Offer", COMPOSE_OFFER, 1900, 560),
    gmail("g2", "Send Waitlist Offer (Gmail)", "={{ $json.waitlistEmail }}", 2120, 560),
    code("o1", "Offer Result", OFFER_RESULT, 2340, 560),
    code("w1", "Waitlist Row", WAITLIST_ROW, 2560, 560),
    sheet_update("u3", "Update Waitlist", "Waitlist", "waitlistId", 2780, 560),
    code("p1", "Cancelled Patient Row", PATIENT_ROW, 2560, 760),
    sheet_update("u2", "Update Cancelled Booking", "Patients", "Booking ID", 2780, 760),
    {"id": "e1", "name": "Get Calendar Event", "type": "n8n-nodes-base.googleCalendar", "typeVersion": 1.3, "position": [1240, 1180],
     "credentials": GCAL, **RETRY, "onError": "continueRegularOutput", "alwaysOutputData": True,
     "parameters": {"operation": "get", "calendar": PRIMARY, "eventId": "={{ $json.calendarEventId }}", "options": {}}},
    code("e2", "Pick Events To Mark", PICK_EVENTS, 1460, 1180),
    {"id": "e3", "name": "Mark Event Cancelled", "type": "n8n-nodes-base.googleCalendar", "typeVersion": 1.3, "position": [1680, 1180],
     "credentials": GCAL, **RETRY,
     "parameters": {"operation": "update", "calendar": PRIMARY, "eventId": "={{ $json.calendarEventId }}",
                    "updateFields": {"summary": "={{ $json.newSummary }}", "description": "={{ $json.newDescription }}", "color": "8", "showMeAs": "transparent"}}},
]
edges = [("Every Hour", "Clinic Config"), ("Run Now (test link)", "Clinic Config"), ("Clinic Config", "Read Patients"),
         ("Read Patients", "Find Due Work"), ("Find Due Work", "Is Reminder?"),
         ("Is Reminder?", "Compose Reminder", 0), ("Is Reminder?", "New Cancellation?", 1),
         ("Compose Reminder", "Send Reminder (Gmail)"), ("Send Reminder (Gmail)", "Reminder Row"), ("Reminder Row", "Mark Reminder Sent"),
         ("New Cancellation?", "Read Waitlist", 0), ("New Cancellation?", "Get Calendar Event", 1),
         ("Read Waitlist", "Match Waitlist"), ("Match Waitlist", "Someone Waiting?"),
         ("Someone Waiting?", "Compose Waitlist Offer", 0), ("Someone Waiting?", "Cancelled Patient Row", 1),
         ("Compose Waitlist Offer", "Send Waitlist Offer (Gmail)"), ("Send Waitlist Offer (Gmail)", "Offer Result"),
         ("Offer Result", "Waitlist Row"), ("Offer Result", "Cancelled Patient Row"),
         ("Waitlist Row", "Update Waitlist"), ("Cancelled Patient Row", "Update Cancelled Booking"),
         ("Get Calendar Event", "Pick Events To Mark"), ("Pick Events To Mark", "Mark Event Cancelled")]
dump("BookWell – Reminders & Waitlist", nodes, connect(edges), settings(ERROR_WF))
