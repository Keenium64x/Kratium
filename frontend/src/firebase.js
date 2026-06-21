import { initializeApp } from "firebase/app";
import {
  getMessaging,
  isSupported,
  onMessage,
  onRegistered,
  register,
} from "firebase/messaging";

const firebaseConfig = {
  apiKey: "AIzaSyBh9fwqcVpMN5SFNG6EH9q9ovo4cDbmXzA",
  authDomain: "kratium-6238d.firebaseapp.com",
  projectId: "kratium-6238d",
  storageBucket: "kratium-6238d.firebasestorage.app",
  messagingSenderId: "894098574304",
  appId: "1:894098574304:web:c036fa462c84d8a2f03985",
  measurementId: "G-ZFXSMG8X5V",
};

export const firebaseVapidKey =
  import.meta.env.VITE_FIREBASE_VAPID_KEY ||
  "BH-rCzskY5Qt5KK52kDZsCN8sz95jIdHccX_PjshclWdHQWFig6WgE07s0pJ3R1-9Pl15oY8twI7GHYHxGXgHxs";

const app = initializeApp(firebaseConfig);
const BASE_URL = window.location.origin;
const SERVICE_WORKER_URL = import.meta.env.DEV
  ? "/firebase-messaging-sw.js"
  : "/assets/kratium/frontend/firebase-messaging-sw.js";

let messagingInstance = null;
let serviceWorkerRegistrationPromise = null;
let messagingRegistrationPromise = null;
let registeredListenerUnsubscribe = null;
let foregroundListenerUnsubscribe = null;
const registrationListeners = new Set();

export async function getBrowserMessagingSupport() {
  const checks = {
    secureContext: window.isSecureContext,
    cookies: navigator.cookieEnabled,
    indexedDB: "indexedDB" in window,
    serviceWorker: "serviceWorker" in navigator,
    pushManager: "PushManager" in window,
    notification: "Notification" in window,
    fetch: "fetch" in window,
    showNotification:
      typeof ServiceWorkerRegistration !== "undefined" &&
      "showNotification" in ServiceWorkerRegistration.prototype,
    pushSubscriptionGetKey:
      typeof PushSubscription !== "undefined" &&
      "getKey" in PushSubscription.prototype,
  };

  try {
    await new Promise((resolve, reject) => {
      const request = indexedDB.open("firebase-support-test");
      request.onerror = () => reject(request.error);
      request.onblocked = () =>
        reject(new Error("IndexedDB open request was blocked"));
      request.onsuccess = () => {
        request.result.close();
        indexedDB.deleteDatabase("firebase-support-test");
        resolve();
      };
    });
    checks.indexedDBOpenable = true;
  } catch (error) {
    checks.indexedDBOpenable = false;
    checks.indexedDBError = error?.message || String(error);
  }

  let firebaseSupported = false;
  try {
    firebaseSupported = await isSupported();
  } catch (error) {
    checks.firebaseError = error?.message || String(error);
  }

  const failedChecks = Object.entries(checks)
    .filter(([name, value]) => name !== "indexedDBError" && name !== "firebaseError" && !value)
    .map(([name]) => name);

  return {
    supported: firebaseSupported,
    failedChecks,
    checks,
  };
}

async function getMessagingInstance() {
  const support = await getBrowserMessagingSupport();
  if (!support.supported) return null;
  if (!messagingInstance) {
    messagingInstance = getMessaging(app);
  }
  return messagingInstance;
}

function waitForServiceWorkerActivation(registration) {
  if (registration.active) return Promise.resolve(registration);

  const worker = registration.installing || registration.waiting;
  if (!worker) return Promise.resolve(registration);

  return new Promise((resolve, reject) => {
    const handleStateChange = () => {
      if (worker.state === "activated") {
        worker.removeEventListener("statechange", handleStateChange);
        resolve(registration);
      } else if (worker.state === "redundant") {
        worker.removeEventListener("statechange", handleStateChange);
        reject(new Error("Firebase service worker became redundant"));
      }
    };

    worker.addEventListener("statechange", handleStateChange);
    handleStateChange();
  });
}

export async function getFirebaseServiceWorkerRegistration() {
  if (!serviceWorkerRegistrationPromise) {
    serviceWorkerRegistrationPromise = (async () => {
      const scriptUrl = new URL(
        SERVICE_WORKER_URL,
        window.location.origin
      ).href;
      const response = await fetch(scriptUrl, { cache: "no-store" });

      if (!response.ok) {
        throw new Error(
          `Service worker was not found: ${response.status} ${scriptUrl}`
        );
      }

      const contentType = response.headers.get("content-type") || "";
      if (!/javascript|ecmascript/i.test(contentType)) {
        throw new Error(
          `Service worker returned "${contentType}" instead of JavaScript: ${scriptUrl}`
        );
      }

      const registrations = await navigator.serviceWorker.getRegistrations();
      let registration = registrations.find((item) =>
        [item.active, item.waiting, item.installing].some(
          (worker) => worker?.scriptURL === scriptUrl
        )
      );

      if (registration) {
        await registration.update();
      } else {
        registration = await navigator.serviceWorker.register(scriptUrl);
      }

      return waitForServiceWorkerActivation(registration);
    })().catch((error) => {
      serviceWorkerRegistrationPromise = null;
      throw error;
    });
  }

  return serviceWorkerRegistrationPromise;
}

export async function registerBrowserMessaging(onRegistration) {
  const messaging = await getMessagingInstance();
  if (!messaging) {
    console.warn("Firebase Messaging is not supported in this browser");
    return () => {};
  }

  if (onRegistration) registrationListeners.add(onRegistration);

  if (!registeredListenerUnsubscribe) {
    registeredListenerUnsubscribe = onRegistered(
      messaging,
      (installationId) => {
        localStorage.setItem(
          "kratium_firebase_installation_id",
          installationId
        );

        for (const listener of registrationListeners) {
          Promise.resolve(listener(installationId)).catch((error) => {
            console.error("Failed to sync Firebase installation ID", error);
          });
        }
      }
    );
  }

  const serviceWorkerRegistration =
    await getFirebaseServiceWorkerRegistration();

  if (!messagingRegistrationPromise) {
    messagingRegistrationPromise = register(messaging, {
      vapidKey: firebaseVapidKey,
      serviceWorkerRegistration,
    }).catch((error) => {
      messagingRegistrationPromise = null;
      throw error;
    });
  }

  await messagingRegistrationPromise;

  if (!foregroundListenerUnsubscribe) {
    foregroundListenerUnsubscribe = onMessage(
      messaging,
      async (payload) => {
        if (Notification.permission !== "granted") return;

        const data = payload.data || {};
        const title =
          payload.notification?.title || data.title || "Kratium";
        const body = payload.notification?.body || data.body || "";
        const route = data.route;
        const url = route
          ? `${BASE_URL}${route.startsWith("/") ? route : `/${route}`}`
          : BASE_URL;
        const registration =
          await getFirebaseServiceWorkerRegistration();

        await registration.showNotification(title, {
          body,
          icon: "/Kratium Icon.jpg",
          badge: "/Kratium Icon.jpg",
          tag: data.notification_id || undefined,
          data: { url },
        });
      }
    );
  }

  return () => {
    if (onRegistration) registrationListeners.delete(onRegistration);
  };
}
