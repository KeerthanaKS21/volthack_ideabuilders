/**
 * GridLite Centralized API Client Service
 * Connects frontend dashboard with deployed backend (Render / Local).
 */

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'https://gridlite-backend.onrender.com'
).replace(/\/+$/, '')

/**
 * Standard fetch wrapper with timeout support for handling slow connections or Render cold starts.
 */
async function fetchApi(endpoint, options = {}, timeoutMs = 20000) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Accept': 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
    clearTimeout(timeoutId)
    return response
  } catch (err) {
    clearTimeout(timeoutId)
    if (err.name === 'AbortError') {
      throw new Error(`Request to ${endpoint} timed out after ${timeoutMs / 1000}s.`)
    }
    throw err
  }
}

export const api = {
  baseUrl: API_BASE_URL,

  // Health / Connection Check
  checkHealth: async () => {
    const res = await fetchApi('/api/health')
    if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`)
    return res.json()
  },

  // Machines
  getMachines: async () => {
    const res = await fetchApi('/api/machines')
    if (!res.ok) throw new Error(`Failed to load machines: HTTP ${res.status}`)
    return res.json()
  },
  getMachineReadings: async (machineId, limit = 50) => {
    const res = await fetchApi(`/api/machines/${encodeURIComponent(machineId)}/readings?limit=${limit}`)
    if (!res.ok) return []
    return res.json()
  },
  getMachineChanges: async (machineId) => {
    const res = await fetchApi(`/api/machines/${encodeURIComponent(machineId)}/changes`)
    if (!res.ok) return []
    return res.json()
  },

  // Live Telemetry
  getLatestReadings: async () => {
    const res = await fetchApi('/api/readings/latest')
    if (!res.ok) throw new Error(`Failed to load latest readings: HTTP ${res.status}`)
    return res.json()
  },

  // Energy Intelligence
  getEnergyOverview: async () => {
    const res = await fetchApi('/api/energy/overview')
    if (!res.ok) throw new Error(`Failed to load energy overview: HTTP ${res.status}`)
    return res.json()
  },
  getTariffConfig: async () => {
    const res = await fetchApi('/api/energy/config')
    if (!res.ok) throw new Error(`Failed to load tariff config: HTTP ${res.status}`)
    return res.json()
  },
  updateTariff: async (tariff) => {
    const res = await fetchApi('/api/energy/config', {
      method: 'PUT',
      body: JSON.stringify({ tariff: parseFloat(tariff) }),
    })
    if (!res.ok) throw new Error(`Failed to update tariff: HTTP ${res.status}`)
    return res.json()
  },
  getMachineEnergy: async (machineId) => {
    const res = await fetchApi(`/api/energy/machines/${encodeURIComponent(machineId)}`)
    if (!res.ok) return null
    return res.json()
  },
  getMachineEnergySummary: async (machineId, hours = 24) => {
    const res = await fetchApi(`/api/energy/machines/${encodeURIComponent(machineId)}/summary?hours=${hours}`)
    if (!res.ok) return null
    return res.json()
  },

  // Diagnosis Engine
  getDiagnosisOverview: async () => {
    const res = await fetchApi('/api/diagnosis/overview')
    if (!res.ok) throw new Error(`Failed to load diagnosis overview: HTTP ${res.status}`)
    return res.json()
  },
  getMachineDiagnosis: async (machineId) => {
    const res = await fetchApi(`/api/diagnosis/machines/${encodeURIComponent(machineId)}`)
    if (!res.ok) return null
    return res.json()
  },
  updateDiagnosisReview: async (eventId, reviewStatus, notes = '') => {
    const res = await fetchApi(`/api/diagnosis/events/${encodeURIComponent(eventId)}/review`, {
      method: 'PUT',
      body: JSON.stringify({ review_status: reviewStatus, notes }),
    })
    if (!res.ok) throw new Error(`Failed to update diagnosis review: HTTP ${res.status}`)
    return res.json()
  },

  // Health & Priority Engine
  getHealthOverview: async () => {
    const res = await fetchApi('/api/health/overview')
    if (!res.ok) throw new Error(`Failed to load health overview: HTTP ${res.status}`)
    return res.json()
  },
  getMachineHealth: async (machineId) => {
    const res = await fetchApi(`/api/health/machines/${encodeURIComponent(machineId)}`)
    if (!res.ok) return null
    return res.json()
  },
  updateHealthOperatorStatus: async (eventId, status) => {
    const res = await fetchApi(`/api/health/events/${encodeURIComponent(eventId)}/status`, {
      method: 'PUT',
      body: JSON.stringify({ operator_status: status }),
    })
    if (!res.ok) throw new Error(`Failed to update operator status: HTTP ${res.status}`)
    return res.json()
  },

  // Unified Events Feed
  getRecentEvents: async (limit = 50) => {
    const res = await fetchApi(`/api/events/recent?limit=${limit}`)
    if (!res.ok) throw new Error(`Failed to load recent events: HTTP ${res.status}`)
    return res.json()
  },
  getMachineTimeline: async (machineId, limit = 20) => {
    const res = await fetchApi(`/api/events/machines/${encodeURIComponent(machineId)}/timeline?limit=${limit}`)
    if (!res.ok) return []
    return res.json()
  },
  acknowledgeEvent: async (eventId) => {
    const res = await fetchApi(`/api/events/${encodeURIComponent(eventId)}/acknowledge`, { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to acknowledge event: HTTP ${res.status}`)
    return res.json()
  },
  resolveEvent: async (eventId) => {
    const res = await fetchApi(`/api/events/${encodeURIComponent(eventId)}/resolve`, { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to resolve event: HTTP ${res.status}`)
    return res.json()
  },

  // AI Assistant (Grounded & Evidence-Backed)
  getQuickQuestions: async () => {
    const res = await fetchApi('/api/assistant/quick-questions')
    if (!res.ok) return []
    return res.json()
  },
  queryAssistant: async (question, conversationId) => {
    const res = await fetchApi('/api/assistant/query', {
      method: 'POST',
      body: JSON.stringify({ question, conversation_id: conversationId }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Assistant service responded with HTTP ${res.status}`)
    }
    return res.json()
  },
  clearConversation: async (conversationId) => {
    if (!conversationId) return
    try {
      await fetchApi(`/api/assistant/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' })
    } catch {}
  },

  // Anomaly Model Retraining
  trainAnomalyModel: async (machineId) => {
    const res = await fetchApi(`/api/anomaly/train/${encodeURIComponent(machineId)}`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || `Model training failed with HTTP ${res.status}`)
    }
    return data
  },

  // Baseline
  getMachineBaseline: async (machineId) => {
    const res = await fetchApi(`/api/change-detection/baseline/${encodeURIComponent(machineId)}`)
    if (!res.ok) return null
    return res.json()
  },

  // Demo & Fault Injection
  resetDemo: async () => {
    const res = await fetchApi('/api/demo/reset', { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to reset demo state: HTTP ${res.status}`)
    return res.json()
  },
  injectFault: async (machineId, faultType = 'MECHANICAL_DEGRADATION') => {
    const res = await fetchApi(`/api/demo/inject-fault?machine_id=${encodeURIComponent(machineId)}&fault_type=${encodeURIComponent(faultType)}`, { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to inject fault: HTTP ${res.status}`)
    return res.json()
  },
  clearFaults: async () => {
    const res = await fetchApi('/api/demo/clear-faults', { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to clear faults: HTTP ${res.status}`)
    return res.json()
  },
}
