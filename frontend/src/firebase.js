import { initializeApp } from 'firebase/app'
import { getAnalytics } from "firebase/analytics";
import { getMessaging, getToken, onMessage } from 'firebase/messaging'

const firebaseConfig = {
  apiKey: "AIzaSyBh9fwqcVpMN5SFNG6EH9q9ovo4cDbmXzA",
  authDomain: "kratium-6238d.firebaseapp.com",
  projectId: "kratium-6238d",
  storageBucket: "kratium-6238d.firebasestorage.app",
  messagingSenderId: "894098574304",
  appId: "1:894098574304:web:d18715699f80dd7ef03985",
  measurementId: "G-89D56E8XQW"
};

const app = initializeApp(firebaseConfig)
const analytics = getAnalytics(app);

export const messaging = getMessaging(app)
getToken(messaging, {vapidKey: "BH-rCzskY5Qt5KK52kDZsCN8sz95jIdHccX_PjshclWdHQWFig6WgE07s0pJ3R1-9Pl15oY8twI7GHYHxGXgHxs"})

export default app

onMessage(messaging, (payload) => {
  console.log('FCM foreground message:', payload)

  new Notification(payload.notification.title, {
    body: payload.notification.body
  })
})