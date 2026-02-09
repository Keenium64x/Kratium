import frappe
import requests
from icalendar import Calendar
from frappe.utils import get_datetime, now_datetime

ICAL_URL = "https://scientia-eu-v3-3-0-api-d4-03.azurewebsites.net//api/ical/..."


def sync_all_ical_sources():
    sync_ical_url(ICAL_URL)


def sync_ical_url(url: str):
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    cal = Calendar.from_ical(resp.text)
    seen_uids = set()

    for component in cal.walk("VEVENT"):
        uid = str(component.get("UID"))
        seen_uids.add(uid)

        doc = get_or_create(uid, url)

        doc.title = str(component.get("SUMMARY", ""))
        doc.description = str(component.get("DESCRIPTION", ""))
        doc.location = str(component.get("LOCATION", ""))

        doc.starts_at = normalize_dt(component.get("DTSTART"))
        doc.ends_at = normalize_dt(component.get("DTEND"))

        doc.last_synced = now_datetime()
        doc.save(ignore_permissions=True)

    handle_removed_events(url, seen_uids)


def get_or_create(uid, url):
    name = frappe.db.get_value(
        "External Calendar Event",
        {"external_uid": uid},
        "name"
    )

    if name:
        return frappe.get_doc("External Calendar Event", name)

    doc = frappe.new_doc("External Calendar Event")
    doc.external_uid = uid
    doc.source_url = url
    return doc


def normalize_dt(ical_dt):
    if not ical_dt:
        return None
    return get_datetime(ical_dt.dt)


def handle_removed_events(url, active_uids):
    stale = frappe.get_all(
        "External Calendar Event",
        filters={
            "source_url": url,
            "external_uid": ["not in", list(active_uids)]
        },
        pluck="name"
    )

    for name in stale:
        # choose one:
        frappe.delete_doc("External Calendar Event", name)
        # OR mark cancelled instead
