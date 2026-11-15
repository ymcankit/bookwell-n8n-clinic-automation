"""Error workflow: any BookWell workflow that fails emails staff a link to the failed run (which holds the submitted data).
usage: python3 build_error.py <gmailCredId>"""
import sys
from common import *

GMAIL = creds("gmailOAuth2", sys.argv[1])

COMPOSE = ESC_JS + r"""
const e = $('On Workflow Error').first().json;
const C = $('Clinic Config').first().json;
const to = C.staffEmail || $json.emailAddress;
const wf = e.workflow || {}, ex = e.execution || {};
const link = ex.url || (ex.id ? `http://localhost:5678/workflow/${wf.id}/executions/${ex.id}` : '');
const html = `<div style="font-family:Arial,sans-serif;max-width:560px">
  <h3 style="color:#b42318">🔴 A BookWell automation failed</h3>
  <p><b>Workflow:</b> ${esc(wf.name)}<br><b>Failed at node:</b> ${esc(ex.lastNodeExecuted || 'unknown')}<br>
  <b>Error:</b> ${esc(ex.error?.message || e.trigger?.error?.message || 'unknown error')}</p>
  ${link ? `<p><a href="${esc(link)}">Open the failed run in n8n</a> — the input data (e.g. the patient's submitted details) is in the run. Please follow up manually.</p>` : ''}
  <p style="font-size:11px;color:#888">BookWell demo – fictional data.</p></div>`;
return [{ json: { to, subject: `[BookWell ERROR] ${wf.name || 'workflow'} failed`, html } }];"""

nodes = [
    sticky("s1", "## Error alert\nEvery BookWell workflow points here (Workflow settings → Error workflow).\nIf any step fails after retries, staff get an email with a link to the failed run (which holds the submitted details).\nLimitation: it uses the same Gmail account, so a Gmail outage can't alert itself. Add Slack/SMTP as a second channel in production.", -40, -160, 820, 140, 3),
    {"id": "t", "name": "On Workflow Error", "type": "n8n-nodes-base.errorTrigger", "typeVersion": 1, "position": [0, 60], "parameters": {}},
    config_node(220, 60),
    {"id": "h", "name": "Get Clinic Inbox Address", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [440, 60],
     "credentials": GMAIL, "parameters": INBOX_LOOKUP, **RETRY},
    code("c", "Compose Error Alert", COMPOSE, 660, 60),
    {"id": "g", "name": "Email Staff (Gmail)", "type": "n8n-nodes-base.gmail", "typeVersion": 2.1, "position": [880, 60], "credentials": GMAIL, **RETRY,
     "parameters": {"resource": "message", "operation": "send", "sendTo": "={{ $json.to }}", "subject": "={{ $json.subject }}",
                    "emailType": "html", "message": "={{ $json.html }}", "options": {"appendAttribution": False, "senderName": "={{ $('Clinic Config').first().json.clinicName + ' – Alerts' }}"}}},
]
dump(ERROR_WORKFLOW_NAME, nodes, connect([("On Workflow Error", "Clinic Config"), ("Clinic Config", "Get Clinic Inbox Address"),
                                         ("Get Clinic Inbox Address", "Compose Error Alert"), ("Compose Error Alert", "Email Staff (Gmail)")]), settings())
