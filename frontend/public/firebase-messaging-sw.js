const BASE_URL = self.location.origin;

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch (_) {
    payload = { data: { body: event.data.text() } };
  }

  const data = payload.data || {};
  const title = payload.notification?.title || data.title || "Kratium";
  const body = payload.notification?.body || data.body || "";
  const route = data.route;
  const url = route
    ? `${BASE_URL}${route.startsWith("/") ? route : `/${route}`}`
    : BASE_URL;

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/Kratium Icon.jpg",
      badge: "/Kratium Icon.jpg",
      tag: data.notification_id || undefined,
      data: { url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification?.data?.url || BASE_URL;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(async (windows) => {
        const existingWindow = windows.find(
          (windowClient) => windowClient.url === url
        );
        if (existingWindow) {
          await existingWindow.focus();
          return;
        }
        await self.clients.openWindow(url);
      })
  );
});
