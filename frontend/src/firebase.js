import { initializeApp } from "firebase/app";
import { getMessaging, onMessage } from "firebase/messaging";

const firebaseConfig = {
  apiKey: "AIzaSyBh9fwqcVpMN5SFNG6EH9q9ovo4cDbmXzA",
  authDomain: "kratium-6238d.firebaseapp.com",
  projectId: "kratium-6238d",
  storageBucket: "kratium-6238d.firebasestorage.app",
  messagingSenderId: "894098574304",
  appId: "1:894098574304:web:c036fa462c84d8a2f03985",
  measurementId: "G-ZFXSMG8X5V",
};

const BASE_URL = window.location.origin;

const app = initializeApp(firebaseConfig);
export const messaging = getMessaging(app);

onMessage(messaging, (payload) => {
  const data = payload.data || {};
  const title = payload.notification?.title || data.title || "Kratium";
  const body = payload.notification?.body || data.body || "";
  const route = data.route;
  const url = route ? `${BASE_URL}${route.startsWith("/") ? route : `/${route}`}` : BASE_URL;

  if (Notification.permission !== "granted") return;

  const notification = new Notification(title, {
    body,
    icon: "/Kratium Icon.jpg",
    tag: data.notification_id || undefined,
    data: { url },
  });

  notification.onclick = (e) => {
    e.preventDefault();
    window.open(url, "_blank", "noopener,noreferrer");
  };
});
