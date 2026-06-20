# Kratium notifications and reminders

The system now separates two concerns:

- `kratium.notifications` delivers a notification immediately through Firebase.
- `kratium.reminders` persists a future reminder in Frappe.
- `kratium.tasks.reminders.dispatch_reminders` runs every minute, claims due reminders, and queues delivery.

This means a reminder survives web restarts, worker restarts, and Redis queue loss because its source of truth is the `Reminder Master` document.

## Backend use

Send now through the normal worker queue:

```python
from kratium.notifications import enqueue_notification

enqueue_notification(
	user="Administrator",
	title="Supplier follow-up",
	body="Call Acme about the delayed order.",
	route="/kratium/home",
	data={"reference_doctype": "Action", "reference_name": "ACT-0001"},
)
```

Schedule an exact date:

```python
from kratium.reminders import schedule_reminder

reminder_name = schedule_reminder(
	"Administrator",
	"Submit report",
	"The monthly report is due today.",
	"2026-06-21 09:00:00",
	route="/kratium/home",
)
```

Schedule relative to now:

```python
from kratium.reminders import schedule_reminder_in

reminder_name = schedule_reminder_in(
	"Administrator",
	"Check the oven",
	"The timer has finished.",
	minutes=20,
)
```

Create a repeating follow-up:

```python
reminder_name = schedule_reminder_in(
	"Administrator",
	"Follow up with the client",
	"Confirm whether the proposal was approved.",
	hours=1,
	reminder_type="Follow Up",
	repeat_every="30m",
	data={
		"presentation": "interactive",
		"actions": [
			{"id": "complete", "title": "Completed"},
			{"id": "snooze", "title": "Snooze"},
			{"id": "reschedule", "title": "Reschedule"},
		],
	},
)
```

`Follow Up` repeats until it is cancelled. `Until Completion` repeats while its linked Action is not completed. `Once`, `Before Completion`, and `Snooze` currently deliver once at the supplied `run_at`.

Reschedule or cancel:

```python
from kratium.reminders import cancel_reminder, reschedule_reminder

reschedule_reminder(reminder_name, "2026-06-22 14:30:00")
cancel_reminder(reminder_name)
```

## Frontend API use

Send now:

```javascript
await call("kratium.api.send_notification", {
	title: "Test notification",
	body: "This appears on every registered device.",
	route: "/kratium/home",
	data: { source: "frontend" },
})
```

Schedule:

```javascript
const result = await call("kratium.api.schedule_notification", {
	title: "Tomorrow",
	body: "Remember to make the call.",
	run_at: "2026-06-21 09:00:00",
	route: "/kratium/home",
	reminder_type: "Once",
})
```

Recurring follow-up:

```javascript
await call("kratium.api.schedule_notification", {
	title: "Follow up",
	body: "Has this been completed?",
	run_at: "2026-06-21 09:00:00",
	reminder_type: "Follow Up",
	repeat_every: "15m",
	data: {
		presentation: "interactive",
		actions: [
			{ id: "complete", title: "Completed" },
			{ id: "snooze", title: "Snooze" },
			{ id: "reschedule", title: "Reschedule" },
		],
	},
})
```

The API automatically targets the authenticated user. A non-System Manager cannot send to another user.

## Payload contract

Every device receives string-valued FCM data with:

- `schema_version`
- `event_type`
- `title`
- `body`
- `route`, when supplied
- `notification_id` or `reminder_id`, when applicable
- any custom `data` fields

Objects and arrays, including future action buttons, are JSON-encoded strings.

Native Android/iOS messages include a visible Firebase notification plus the data payload. Web messages remain data-only because the Kratium service worker displays them and handles the click route.

## Scheduler operation

The scheduler job is:

```text
kratium.tasks.reminders.dispatch_reminders
```

It runs with cron `* * * * *`. A reminder can therefore fire up to roughly one minute after `run_at`.

Useful checks:

```bash
bench --site kratium.localhost scheduler status
bench --site kratium.localhost scheduler resume
bench --site kratium.localhost enable-scheduler
bench --site kratium.localhost execute kratium.tasks.reminders.dispatch_reminders
```

Delivery uses these states:

- `Pending`: waiting for its time or a retry
- `Processing`: claimed by the dispatcher
- `Fired`: delivered successfully
- `Failed`: exhausted retries
- `Cancelled`: deliberately stopped

Interrupted `Processing` reminders are recovered after 15 minutes. Failed deliveries retry after 1, 5, 15, 30, and 60 minutes. Invalid Firebase tokens are disabled automatically.

## Recommended Flutter changes

The current mobile repository has notification setup duplicated between `lib/main.dart` and `lib/services/fcm_service.dart`. Consolidate it into one `FcmService`.

1. Add `flutter_local_notifications` to `pubspec.yaml`.
2. In `lib/main.dart`, register a top-level `FirebaseMessaging.onBackgroundMessage` handler before `runApp`.
3. Move token registration, refresh handling, foreground display, tap handling, and initial-message handling into `lib/services/fcm_service.dart`.
4. Read both sources:

   ```dart
   final title = message.notification?.title ?? message.data['title'] ?? 'Kratium';
   final body = message.notification?.body ?? message.data['body'] ?? '';
   ```

5. Use `flutter_local_notifications` for foreground notifications. Let Firebase display ordinary background/terminated notifications so the app does not create duplicates.
6. Parse `message.data['actions']` as JSON. This is the extension point for `Completed`, `Snooze`, and `Reschedule`; the server-side execution endpoints should be added when the execution system is implemented.
7. Add Android 13 notification permission:

   ```xml
   <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
   ```

8. Create an Android notification channel such as `kratium_reminders` with high importance, sound, vibration, and public lock-screen visibility.
9. Configure APNs, Push Notifications capability, and Background Modes/remote notifications for iOS.
10. Replace the hard-coded ngrok URL with a build-time configuration.

Normal phone notifications will mirror to a paired smartwatch with title and description. A full smartwatch popup with application buttons is a separate Wear OS/watchOS interaction layer; the `event_type`, `presentation`, `notification_id`, and JSON `actions` fields are already available for that future layer.
