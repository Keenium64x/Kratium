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

const BASE_URL = "http://kratium.localhost:8083"; 

const app = initializeApp(firebaseConfig);
export const messaging = getMessaging(app);

onMessage(messaging, (payload) => {
  const { title, body, route } = payload.data || {};
  const url = route ? `${BASE_URL}${route.startsWith("/") ? route : `/${route}`}` : BASE_URL;

  const notification = new Notification(title || "Notification", {
    body,
    data: { url },
  });

  notification.onclick = (e) => {
    e.preventDefault();
    window.open(url, "_blank", "noopener,noreferrer");
  };
});