let dockviewApi = null

export function setDockviewApi(api) {
  dockviewApi = api
}

export function getDockviewApi() {
  if (!dockviewApi) {
    throw new Error('Dockview API not initialized yet')
  }
  return dockviewApi
}