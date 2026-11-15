"""Shared pieces for the BookWell n8n workflow builders: clinic config, credential refs, node helpers."""
import json

# ---- Clinic settings: the ONLY place clinic details live. They become a "Clinic Config" node in each workflow. ----
CLINIC = {
    "clinicName": "BookWell Family Clinic",
    "clinicTimezone": "America/New_York",
    "spreadsheetId": "PASTE_YOUR_SPREADSHEET_ID",
    "address": "1420 Maple Grove Avenue, Suite 200, Riverton",
    "phone": "(555) 014-2290",
    "hoursText": "Mon–Fri 8:00 AM–6:00 PM, Sat 9:00 AM–1:00 PM, closed Sundays",
    "morningWindow": "8:00 AM – 12:00 PM",
    "afternoonWindow": "1:00 PM – 6:00 PM",
    "lateCancelFee": "$25",
    "visitNotes": "Free parking behind the building. Please bring your insurance card and a photo ID.",
    "staffEmail": "",    # blank = send staff alerts to the Gmail inbox n8n is signed in as
    "managerEmail": "",  # blank = same fallback for the weekly summary
    "faq": """- Address: 1420 Maple Grove Avenue, Suite 200, Riverton. Free parking behind the building; wheelchair accessible.
- Phone: (555) 014-2290. Email: hello@bookwell.example
- Hours: Mon–Fri 8:00 AM–6:00 PM, Sat 9:00 AM–1:00 PM, closed Sundays and public holidays.
- Appointment windows: Morning = 8:00 AM–12:00 PM, Afternoon = 1:00 PM–6:00 PM (Saturday mornings only).
- Insurance: we accept BrightPath Health, Meridian Care, Unity Shield and Harbor Mutual plans, plus self-pay. Bring your insurance card and a photo ID. Self-pay visits start at $85.
- New patients: arrive 15 minutes early to complete forms; bring a list of current medications.
- Cancellation policy: cancel or reschedule at least 24 hours ahead by phone or by replying to your confirmation email. Late cancellations and no-shows may incur a $25 fee.
- Requests are tentative until a staff member confirms the exact time by email within one business day.
- Prescription refills and test results are handled by phone, not by email.""",
}

ERROR_WORKFLOW_NAME = "BookWell – Error Alert"


def config_node(x, y, node_id="cfg"):
    return {"id": node_id, "name": "Clinic Config", "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [x, y],
            "parameters": {"mode": "manual", "includeOtherFields": True, "options": {},
                           "assignments": {"assignments": [
                               {"id": f"cfg{i}", "name": k, "type": "string", "value": v} for i, (k, v) in enumerate(CLINIC.items())]}}}


def creds(kind, cred_id):
    names = {"anthropicApi": "Anthropic account", "googleCalendarOAuth2Api": "Google Calendar account",
             "googleSheetsOAuth2Api": "Google Sheets account", "gmailOAuth2": "Gmail account"}
    return {kind: {"id": cred_id, "name": names[kind]}}


def code(node_id, name, js, x, y, **extra):
    n = {"id": node_id, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [x, y], "parameters": {"jsCode": js}}
    n.update(extra)
    return n


def sticky(node_id, content, x, y, w, h, color=7):
    return {"id": node_id, "name": f"Note {node_id}", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [x, y],
            "parameters": {"content": content, "width": w, "height": h, "color": color}}


def if_node(node_id, name, left, op, x, y, right=True):
    operator = {"type": "boolean", "operation": "true", "singleValue": True} if op == "true" else {"type": "string", "operation": "equals"}
    cond = {"id": node_id + "c", "leftValue": left, "operator": operator}
    if op != "true":
        cond["rightValue"] = right
    else:
        cond["rightValue"] = True
    return {"id": node_id, "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [x, y],
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                                          "conditions": [cond], "combinator": "and"}, "options": {}}}


def doc_ref():
    return {"__rl": True, "mode": "id", "value": "={{ $('Clinic Config').first().json.spreadsheetId }}"}


def tab(name):
    return {"__rl": True, "mode": "name", "value": name}


RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000}

INBOX_LOOKUP = {"method": "GET", "url": "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2", "options": {}}

ESC_JS = r"""const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));"""


def connect(edges):
    """edges: (from, to) or (from, to, output_index)"""
    conn = {}
    for e in edges:
        a, b, o = (e + (0,))[:3] if len(e) == 2 else e
        outs = conn.setdefault(a, {"main": []})["main"]
        while len(outs) <= o:
            outs.append([])
        outs[o].append({"node": b, "type": "main", "index": 0})
    return conn


def settings(error_wf_id=None):
    s = {"executionOrder": "v1", "timezone": CLINIC["clinicTimezone"], "saveDataSuccessExecution": "all", "saveManualExecutions": True}
    if error_wf_id:
        s["errorWorkflow"] = error_wf_id
    return s


def dump(name, nodes, conn, sett):
    print(json.dumps({"name": name, "nodes": nodes, "connections": conn, "settings": sett}, indent=2, ensure_ascii=False))
