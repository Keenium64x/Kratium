import { createApp } from "vue"

import App from "./App.vue"
import router from "./router"
import { initSocket } from "./socket"

import {
	Alert,
	Badge,
	Button,
	Dialog,
	ErrorMessage,
	FormControl,
	Input,
	TextInput,
	frappeRequest,
	pageMetaPlugin,
	resourcesPlugin,
	setConfig,
} from "frappe-ui"
import VueDnDKitPlugin from '@vue-dnd-kit/core';

import "./index.css"

import Toast, {POSITION} from "vue-toastification";
import "vue-toastification/dist/index.css";

const options = {
	timeout: 5000,
	position: POSITION.BOTTOM_RIGHT
};

const globalComponents = {
	Button,
	TextInput,
	Input,
	FormControl,
	ErrorMessage,
	Dialog,
	Alert,
	Badge,
}

const app = createApp(App)

setConfig("resourceFetcher", frappeRequest)

app.use(router)
app.use(resourcesPlugin)
app.use(pageMetaPlugin)
app.use(Toast, options);

const socket = initSocket()
app.config.globalProperties.$socket = socket

for (const key in globalComponents) {
	app.component(key, globalComponents[key])
}

app.use(VueDnDKitPlugin);

app.mount("#app")
