importScripts("https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyBh9fwqcVpMN5SFNG6EH9q9ovo4cDbmXzA",
  authDomain: "kratium-6238d.firebaseapp.com",
  projectId: "kratium-6238d",
  storageBucket: "kratium-6238d.firebasestorage.app",
  messagingSenderId: "894098574304",
  appId: "1:894098574304:web:c036fa462c84d8a2f03985",
  measurementId: "G-ZFXSMG8X5V",
});

const BASE_URL = "https://yourdomain.com"; // <-- change once

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const { title, body, route } = payload.data || {};
  const url = route ? `${BASE_URL}${route.startsWith("/") ? route : `/${route}`}` : BASE_URL;

  self.registration.showNotification(title || "Notification", {
    body,
    data: { url },
  });
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification?.data?.url || BASE_URL;
  event.waitUntil(clients.openWindow(url));
});