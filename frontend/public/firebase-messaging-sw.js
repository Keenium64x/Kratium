importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyBh9fwqcVpMN5SFNG6EH9q9ovo4cDbmXzA",
  authDomain: "kratium-6238d.firebaseapp.com",
  projectId: "kratium-6238d",
  messagingSenderId: "894098574304",
  appId: "1:894098574304:web:d18715699f80dd7ef03985",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('[SW] Background message:', payload);

  self.registration.showNotification(
    payload.notification?.title ?? 'Notification',
    {
      body: payload.notification?.body ?? '',
      icon: '/icon.png'
    }
  );
});