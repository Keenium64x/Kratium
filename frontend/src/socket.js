import { io } from "socket.io-client"
import { socketio_port } from "../../../../sites/common_site_config.json"

let socket = null

export function initSocket() {
  const host = window.location.hostname
  const port = socketio_port ? `:${socketio_port}` : ""
  const protocol = window.location.protocol === "https:" ? "https" : "http"

  const url = `${protocol}://${host}${port}`

  socket = io(url, {
    withCredentials: true,
    transports: ["websocket"],
    reconnectionAttempts: 5,
  })

  return socket
}

export function useSocket() {
  return socket
}