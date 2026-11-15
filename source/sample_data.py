"""Fictional sample data for the BookWell demo: one realistic week (Nov 9–16, 2026) as the workflows would have recorded it.
All people are made up; emails use the reserved example.com domain; phones use the fictional 555-01xx range.
Every row is already 'processed' (reminders sent, cancellations handled), so the live hourly workflow has nothing to send."""
import csv, json, sys
from datetime import datetime, timedelta, timezone

NY = timezone(timedelta(hours=-5))  # clinic time (EST in November)
TEMPL = {
    "health": "Thank you for letting us know. We can't give medical advice by email, so a member of our care team will review your message and contact you within one business day. If your symptoms get worse or this is an emergency, call 911 or your local emergency number right away.",
    "urgent": "Please don't wait for an appointment. If this is a medical emergency or you are in immediate danger, call 911 (or your local emergency number) now. If you are having thoughts of harming yourself, you can call or text 988 (Suicide & Crisis Lifeline, US) at any time. We have flagged your message to our care team as urgent.",
    "other": "Thanks for your question. Our front desk will get back to you within one business day.",
}
DUR = {"New patient visit": 45, "Annual check-up": 40, "Follow-up": 20, "Other": 30}

# name, email, phone-suffix, reason, submitted (NY), appt date, window, question, category, faq answer, status, slot issue
P = [
    ("Lucas Silva", "lucas.silva", "3101", "Annual check-up", "2026-11-09 08:14", "2026-11-10", "Morning", "What are your Saturday hours?", "faq",
     "We're open Saturdays from 9:00 AM to 1:00 PM, and Saturday appointments are mornings only.", "Confirmed", ""),
    ("Chloe Dubois", "chloe.dubois", "3102", "Annual check-up", "2026-11-09 10:32", "2026-11-10", "Afternoon", "Do you accept Medicare?", "other", "", "Confirmed", ""),
    ("Emily Carter", "emily.carter", "3103", "New patient visit", "2026-11-09 12:05", "2026-11-11", "Morning", "Do you accept BrightPath Health insurance?", "faq",
     "Yes, we accept BrightPath Health plans. Please bring your insurance card and a photo ID to your visit.", "Confirmed", ""),
    ("James Wilson", "james.wilson", "3104", "New patient visit", "2026-11-09 17:48", "2026-11-11", "Afternoon", "", "none", "", "Cancelled – slot offered to WL-002", ""),
    ("Marcus Lee", "marcus.lee", "3105", "Follow-up", "2026-11-10 09:20", "2026-11-12", "Afternoon", "", "none", "", "Confirmed", ""),
    ("Olivia Brown", "olivia.brown", "3106", "Follow-up", "2026-11-10 13:41", "2026-11-12", "Morning", "Can I get my blood test results by email?", "health", "", "Confirmed", ""),
    ("Sofia Martinez", "sofia.martinez", "3107", "Annual check-up", "2026-11-10 18:02", "2026-11-13", "Morning", "Is there parking at the clinic?", "faq",
     "Yes, there's free parking behind our building at 1420 Maple Grove Avenue, and the clinic is wheelchair accessible.", "Confirmed", ""),
    ("David Okonkwo", "david.okonkwo", "3108", "Other", "2026-11-11 07:55", "2026-11-13", "Afternoon", "My chest has felt tight since yesterday, should I come in sooner?", "health", "", "Confirmed", ""),
    ("Ethan Nguyen", "ethan.nguyen", "3109", "Other", "2026-11-11 21:17", "2026-11-12", "Morning", "I've had chest pain on and off since this morning", "urgent", "", "Confirmed", ""),
    ("Hannah Schmidt", "hannah.schmidt", "3110", "New patient visit", "2026-11-11 11:26", "2026-11-13", "Morning", "What should I bring to my first appointment?", "faq",
     "Please arrive 15 minutes early and bring your insurance card, a photo ID and a list of your current medications.", "Cancelled – slot offered to WL-001", ""),
    ("Raj Patel", "raj.patel", "3111", "Follow-up", "2026-11-12 15:09", "2026-11-14", "Afternoon", "", "none", "", "Cancelled – not offered (slot issue)", "Saturday hours are mornings only"),
    ("Isabella Rossi", "isabella.rossi", "3112", "Annual check-up", "2026-11-13 19:44", "2026-11-15", "Morning", "", "none", "", "Tentative", "Clinic is closed on Sundays"),
    ("Grace Kim", "grace.kim", "3113", "Annual check-up", "2026-11-12 08:37", "2026-11-16", "Morning", "Do you offer flu shots?", "other", "", "Confirmed", ""),
    ("Noah Williams", "noah.williams", "3114", "Follow-up", "2026-11-13 10:12", "2026-11-16", "Afternoon", "", "none", "", "Tentative", ""),
]
IDS = ["K7QF", "M2XA", "P9DL", "T4WB", "A8RC", "H3NV", "C6YE", "R1JS", "Z5GU", "E2MK", "W8HT", "L4PZ", "B9CX", "N3QD"]


def iso(dt): return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def patients():
    rows = []
    for (name, user, ph, reason, sub, day, win, q, cat, faq, status, issue), code in zip(P, IDS):
        sub_dt = datetime.strptime(sub, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        start = datetime.strptime(f"{day} {'09' if win == 'Morning' else '14'}:00", "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        end = start + timedelta(minutes=DUR[reason])
        answer = faq if cat == "faq" else TEMPL.get(cat, "")
        needs = cat in ("health", "urgent", "other") or bool(issue)
        cancelled = status.startswith("Cancelled")
        # anything already inside the 24 h window is marked reminded, so the live hourly job never emails these fictional addresses
        reminded = status in ("Confirmed", "Tentative") and not issue and start - timedelta(hours=24) < datetime.now(NY)
        rows.append({
            "Booking ID": f"BW-{sub_dt:%Y%m%d}-{code}", "Submitted At": iso(sub_dt), "Status": status, "Full Name": name,
            "Email": f"{user}@example.com", "Phone": f"(555) 010-{ph}", "Reason": reason,
            "Preferred Date": day, "Preferred Time": win, "Appointment Start": f"{start:%Y-%m-%d %H:%M}", "Appointment End": f"{end:%Y-%m-%d %H:%M}",
            "Question": q, "AI Answer": answer, "AI Category": cat, "Needs Staff": "YES" if needs else "no", "Slot Issue": issue,
            "Calendar Event ID": "", "Calendar Link": "",
            "Confirmation Sent At": iso(sub_dt + timedelta(seconds=9)),
            "Reminder Sent At": iso(start - timedelta(hours=23, minutes=57)) if reminded and not cancelled else "",
            "Staff Alert Sent At": iso(sub_dt + timedelta(seconds=7)) if needs else "",
        })
    return rows


def waitlist(p):
    by = {r["Full Name"]: r["Booking ID"] for r in p}
    W = [("WL-001", "Maya Chen", "maya.chen", "New patient visit", "Morning", "2026-11-02", f"Offered {by['Hannah Schmidt']}", "2026-11-12T16:00:41.000Z"),
         ("WL-002", "Daniel Brooks", "daniel.brooks", "Follow-up", "Afternoon", "2026-11-03", f"Offered {by['James Wilson']}", "2026-11-10T15:00:38.000Z"),
         ("WL-003", "Aisha Rahman", "aisha.rahman", "Annual check-up", "Morning", "2026-11-05", "Waiting", ""),
         ("WL-004", "Tom Novak", "tom.novak", "Other", "Afternoon", "2026-11-06", "Waiting", ""),
         ("WL-005", "Priya Shah", "priya.shah", "New patient visit", "Morning", "2026-11-09", "Waiting", ""),
         ("WL-006", "Ben Carter", "ben.carter", "Follow-up", "Afternoon", "2026-11-12", "Waiting", "")]
    return [{"waitlistId": i, "fullName": n, "email": f"{u}@example.com", "phone": f"(555) 010-{2000 + k + 1}", "reason": r,
             "preferredTime": t, "addedAt": a, "status": s, "notifiedAt": na} for k, (i, n, u, r, t, a, s, na) in enumerate(W)]


if __name__ == "__main__":
    p = patients(); w = waitlist(p)
    if "--json" in sys.argv:
        print(json.dumps({"patients": p, "waitlist": w}, ensure_ascii=False))
    else:
        out = sys.argv[1]
        for fn, rows in (("patients.csv", p), ("waitlist.csv", w)):
            with open(f"{out}/{fn}", "w", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
        print("wrote", out)
