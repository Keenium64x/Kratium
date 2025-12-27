import { userResource } from "@/data/user"
import { createRouter, createWebHistory } from "vue-router"
import { session } from "./data/session"

const routes = [
  {
    path: "/",
    component: () => import("@/pages/Home.vue"),
    name: "Home",
    children: [
      {
        path: "",
        name: "HomeIndex",
         component: {
        render: () => null,
      },
      },
      {
        path: "gantt",
        name: "Gantt",
        component: () => import("@/components/TimeSystem/Gantt.vue"),
      },
      {
        path: "calendar",
        name: "Calendar",
        component: () => import("@/components/TimeSystem/Calendar/Calendar.vue"),
      },
      {
        path: "todo",
        name: "ToDo",
        component: () => import("@/components/TimeSystem/ToDo/ToDo.vue"),
      },    
    ],
  },
  {
    path: "/account/login",
    name: "Login",
    component: () => import("@/pages/Login.vue"),
  },
]

const router = createRouter({
	history: createWebHistory("/kratium"),
	routes,
})

router.beforeEach(async (to, from, next) => {
	let isLoggedIn = session.isLoggedIn
	try {
		await userResource.promise
	} catch (error) {
		isLoggedIn = false
	}

	if (to.name === "Login" && isLoggedIn) {
		next({ name: "Home" })
	} else if (to.name !== "Login" && !isLoggedIn) {
		next({ name: "Login" })
	} else {
		next()
	}
})

export default router
