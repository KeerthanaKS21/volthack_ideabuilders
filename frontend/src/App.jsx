import React, { useState, useEffect } from 'react'
import { api, API_BASE_URL } from './services/api'

function App() {
  // Global Navigation State
  const [activeNav, setActiveNav] = useState('dashboard') // 'dashboard' | 'machines' | 'events' | 'energy' | 'diagnosis' | 'assistant'
  
  // Data States
  const [machines, setMachines] = useState([])
  const [latestReadings, setLatestReadings] = useState({})
  const [backendStatus, setBackendStatus] = useState('checking') // 'checking' | 'connected' | 'offline'
  const [isLoading, setIsLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(new Date())

  // Anomaly & Model States
  const [selectedMachine, setSelectedMachine] = useState(null)
  const [trainingStatus, setTrainingStatus] = useState('idle') // 'idle' | 'training' | 'success' | 'error'
  const [trainingMessage, setTrainingMessage] = useState('')

  // Behavioral Change States
  const [allChanges, setAllChanges] = useState([])
  const [selectedBaseline, setSelectedBaseline] = useState(null)
  const [selectedHistory, setSelectedHistory] = useState([])

  // Energy States
  const [tariff, setTariff] = useState(8.0)
  const [inputTariff, setInputTariff] = useState('8.0')
  const [energyOverview, setEnergyOverview] = useState(null)
  const [machinesEnergy, setMachinesEnergy] = useState({})
  const [selectedEnergySummary, setSelectedEnergySummary] = useState(null)

  // Diagnosis States
  const [diagnosisOverview, setDiagnosisOverview] = useState(null)
  const [selectedDiagnosis, setSelectedDiagnosis] = useState(null)
  const [isUpdatingReview, setIsUpdatingReview] = useState(false)

  // Health & Priority States
  const [healthOverview, setHealthOverview] = useState(null)
  const [selectedHealth, setSelectedHealth] = useState(null)
  const [isUpdatingOperatorStatus, setIsUpdatingOperatorStatus] = useState(false)

  // Unified Events States
  const [unifiedEvents, setUnifiedEvents] = useState([])
  const [eventFilter, setEventFilter] = useState('ALL') // 'ALL' | 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED'
  const [machineTimeline, setMachineTimeline] = useState([])
  const [isResettingDemo, setIsResettingDemo] = useState(false)
  const [demoResetMessage, setDemoResetMessage] = useState('')

  // Machines Filter & Search
  const [machineSearch, setMachineSearch] = useState('')
  const [machineStatusFilter, setMachineStatusFilter] = useState('ALL') // 'ALL' | 'HEALTHY' | 'WATCH' | 'ATTENTION' | 'CRITICAL'

  // AI Assistant States
  const [assistantMessages, setAssistantMessages] = useState([
    {
      id: 'welcome',
      sender: 'assistant',
      text: "Hello! I am your GridLite Industrial Intelligence Assistant.\n\nYou can ask questions about machine operating status, telemetry readings, anomalies, behavioral changes, energy efficiency, diagnostics, or fleet priority rankings.",
      intent: 'GREETING',
      evidence: [],
      suggestions: [
        "Which machine should I investigate first?",
        "Give me a summary of the factory.",
        "Which machine is wasting the most energy?",
        "Which machines have anomalies?"
      ]
    }
  ])
  const [assistantInput, setAssistantInput] = useState('')
  const [isAssistantLoading, setIsAssistantLoading] = useState(false)
  const [assistantConversationId, setAssistantConversationId] = useState(() => 'conv_' + Math.random().toString(36).substring(2, 9))
  const [quickQuestions, setQuickQuestions] = useState([])
  const [expandedEvidenceMap, setExpandedEvidenceMap] = useState({})

  // ==========================================
  // Helper Formatters & Safe Number Helpers
  // ==========================================

  const safeNumber = (val, decimals = 2, suffix = '') => {
    if (val === null || val === undefined || isNaN(Number(val))) return '-'
    return `${Number(val).toFixed(decimals)}${suffix}`
  }

  const getQuestionText = (q) => {
    if (typeof q === 'string') return q
    if (q && typeof q === 'object') return q.query || q.label || ''
    return ''
  }

  const getQuestionLabel = (q) => {
    if (typeof q === 'string') return q
    if (q && typeof q === 'object') return q.label || q.query || ''
    return ''
  }

  // ==========================================
  // API Fetch Functions
  // ==========================================

  const fetchMachines = async () => {
    try {
      const data = await api.getMachines()
      setMachines(data)
      setBackendStatus('connected')
      await fetchBehaviorChanges(data)
      await fetchMachinesEnergy(data)
    } catch (error) {
      setBackendStatus('offline')
    } finally {
      setIsLoading(false)
      setLastUpdated(new Date())
    }
  }

  const fetchTariffConfig = async () => {
    try {
      const data = await api.getTariffConfig()
      setTariff(data.tariff)
      setInputTariff(data.tariff.toString())
    } catch (error) {
      console.error("Failed to load tariff config:", error)
    }
  }

  const fetchLatestReadings = async () => {
    try {
      const data = await api.getLatestReadings()
      if (Array.isArray(data)) {
        const readingsMap = {}
        data.forEach(r => {
          if (r && r.machine_id) {
            readingsMap[r.machine_id] = r
          }
        })
        setLatestReadings(readingsMap)
      } else if (data && typeof data === 'object') {
        setLatestReadings(data)
      }
      setBackendStatus('connected')
      setLastUpdated(new Date())
    } catch (error) {
      setBackendStatus('offline')
    }
  }

  const fetchBehaviorChanges = async (machineList) => {
    if (!machineList || machineList.length === 0) return
    try {
      const changePromises = machineList.map(async (m) => {
        try {
          return await api.getMachineChanges(m.machine_id)
        } catch {
          return []
        }
      })
      const results = await Promise.all(changePromises)
      const flattened = results.flat()
      setAllChanges(flattened)
    } catch (error) {
      console.error("Failed to fetch behavioral changes:", error)
    }
  }

  const fetchMachinesEnergy = async (machineList) => {
    if (!machineList || machineList.length === 0) return
    try {
      const energyPromises = machineList.map(async (m) => {
        try {
          const data = await api.getMachineEnergy(m.machine_id)
          return data ? { id: m.machine_id, data } : null
        } catch {
          return null
        }
      })
      const results = await Promise.all(energyPromises)
      const energyMap = {}
      results.forEach(item => {
        if (item && item.data) {
          energyMap[item.id] = item.data
        }
      })
      setMachinesEnergy(energyMap)
    } catch (error) {
      console.error("Failed to fetch machines energy:", error)
    }
  }

  const fetchEnergyOverview = async () => {
    try {
      const data = await api.getEnergyOverview()
      setEnergyOverview(data)
    } catch (error) {
      console.error("Failed to load factory energy overview:", error)
    }
  }

  const fetchDiagnosisOverview = async () => {
    try {
      const data = await api.getDiagnosisOverview()
      setDiagnosisOverview(data)
    } catch (error) {
      console.error("Failed to load diagnosis overview:", error)
    }
  }

  const fetchHealthOverview = async () => {
    try {
      const data = await api.getHealthOverview()
      setHealthOverview(data)
    } catch (error) {
      console.error("Failed to load health overview:", error)
    }
  }

  const fetchUnifiedEvents = async () => {
    try {
      const data = await api.getRecentEvents(50)
      setUnifiedEvents(data)
    } catch (error) {
      console.error("Failed to load unified events:", error)
    }
  }

  const fetchQuickQuestions = async () => {
    try {
      const data = await api.getQuickQuestions()
      setQuickQuestions(data)
    } catch (error) {
      console.error("Failed to load quick questions:", error)
    }
  }

  const fetchMachineTimeline = async (machineId) => {
    try {
      const data = await api.getMachineTimeline(machineId, 20)
      setMachineTimeline(data)
    } catch (error) {
      console.error("Failed to load machine event timeline:", error)
    }
  }

  // ==========================================
  // Interactive Handlers
  // ==========================================

  const handleUpdateTariff = async () => {
    const parsed = parseFloat(inputTariff)
    if (isNaN(parsed) || parsed < 0) {
      alert("Please enter a valid positive tariff value.")
      return
    }
    try {
      const data = await api.updateTariff(parsed)
      setTariff(data.tariff)
      fetchEnergyOverview()
      if (machines.length > 0) fetchMachinesEnergy(machines)
    } catch (error) {
      console.error("Failed to update tariff:", error)
    }
  }

  const handleTrainModel = async (machineId) => {
    setTrainingStatus('training')
    setTrainingMessage(`Training Isolation Forest model for ${machineId}...`)
    try {
      const data = await api.trainAnomalyModel(machineId)
      setTrainingStatus('success')
      setTrainingMessage(`Model trained successfully using ${data.training_samples} baseline samples.`)
      await fetchLatestReadings()
    } catch (err) {
      setTrainingStatus('error')
      setTrainingMessage(err.message || 'Training failed.')
    }
  }

  const handleOperatorReview = async (reviewStatus) => {
    if (!selectedDiagnosis || !selectedDiagnosis.event_id) return
    setIsUpdatingReview(true)
    try {
      const data = await api.updateDiagnosisReview(
        selectedDiagnosis.event_id,
        reviewStatus,
        `Operator updated status to ${reviewStatus}`
      )
      setSelectedDiagnosis(prev => ({ ...prev, review_status: data.review_status }))
      fetchDiagnosisOverview()
    } catch (err) {
      console.error("Failed to update operator review:", err)
    } finally {
      setIsUpdatingReview(false)
    }
  }

  const handleHealthOperatorStatus = async (status) => {
    if (!selectedHealth || !selectedHealth.event_id) return
    setIsUpdatingOperatorStatus(true)
    try {
      const data = await api.updateHealthOperatorStatus(selectedHealth.event_id, status)
      setSelectedHealth(prev => ({ ...prev, operator_status: data.operator_status }))
      fetchHealthOverview()
    } catch (err) {
      console.error("Failed to update health operator status:", err)
    } finally {
      setIsUpdatingOperatorStatus(false)
    }
  }

  const handleAcknowledgeEvent = async (eventId) => {
    try {
      await api.acknowledgeEvent(eventId)
      fetchUnifiedEvents()
      if (selectedMachine) fetchMachineTimeline(selectedMachine.machine_id)
    } catch (err) {
      console.error("Failed to acknowledge event:", err)
    }
  }

  const handleResolveEvent = async (eventId) => {
    try {
      await api.resolveEvent(eventId)
      fetchUnifiedEvents()
      if (selectedMachine) fetchMachineTimeline(selectedMachine.machine_id)
    } catch (err) {
      console.error("Failed to resolve event:", err)
    }
  }

  const handleResetDemo = async () => {
    if (!confirm("Are you sure you want to reset the demonstration state to baseline?")) return
    setIsResettingDemo(true)
    setDemoResetMessage('')
    try {
      const data = await api.resetDemo()
      setDemoResetMessage(`Demo reset successful: ${data.cleared_events_count} active events cleared.`)
      await fetchMachines()
      await fetchLatestReadings()
      await fetchDiagnosisOverview()
      await fetchHealthOverview()
      await fetchUnifiedEvents()
      if (selectedMachine) {
        fetchMachineTimeline(selectedMachine.machine_id)
      }
    } catch (err) {
      console.error("Failed to reset demo state:", err)
    } finally {
      setIsResettingDemo(false)
    }
  }

  const handleInjectFault = async (machineId, faultType) => {
    setDemoResetMessage(`Injecting ${faultType.replace(/_/g, ' ')} into ${machineId}...`)
    try {
      await api.injectFault(machineId, faultType)
      setDemoResetMessage(`⚡ Injected ${faultType.replace(/_/g, ' ')} into ${machineId}! Telemetry & anomaly models reacting...`)
      await fetchLatestReadings()
      await fetchHealthOverview()
      await fetchEnergyOverview()
      await fetchDiagnosisOverview()
      await fetchUnifiedEvents()
      if (selectedMachine && selectedMachine.machine_id === machineId) {
        handleOpenMachineDetail(selectedMachine)
      }
    } catch (err) {
      console.error("Failed to inject fault:", err)
      setDemoResetMessage(`Failed to inject fault: ${err.message}`)
    }
  }

  const handleSendAssistantMessage = async (textToSend) => {
    const rawText = textToSend || assistantInput
    const q = getQuestionText(rawText).trim()
    if (!q || isAssistantLoading) return

    const userMsg = {
      id: 'user_' + Date.now(),
      sender: 'user',
      text: q
    }
    setAssistantMessages(prev => [...prev, userMsg])
    setAssistantInput('')
    setIsAssistantLoading(true)

    try {
      const data = await api.queryAssistant(q, assistantConversationId)
      const botMsg = {
        id: 'asst_' + Date.now(),
        sender: 'assistant',
        text: data.answer,
        intent: data.intent,
        evidence: data.evidence || [],
        suggestions: data.suggestions || [],
        machine_id: data.machine_id
      }
      setAssistantMessages(prev => [...prev, botMsg])
    } catch (err) {
      const errorMsg = {
        id: 'asst_err_' + Date.now(),
        sender: 'assistant',
        text: err.message || "Unable to reach the assistant service. Please verify backend connectivity.",
        intent: 'ERROR',
        evidence: [],
        suggestions: ["Give me a factory summary.", "Which machine needs attention?"]
      }
      setAssistantMessages(prev => [...prev, errorMsg])
    } finally {
      setIsAssistantLoading(false)
    }
  }

  const handleClearConversation = async () => {
    await api.clearConversation(assistantConversationId)
    const newId = 'conv_' + Math.random().toString(36).substring(2, 9)
    setAssistantConversationId(newId)
    setAssistantMessages([
      {
        id: 'welcome_' + Date.now(),
        sender: 'assistant',
        text: "Conversation cleared. Ask me anything about machine status, anomalies, energy efficiency, or diagnostic findings.",
        intent: 'GREETING',
        evidence: [],
        suggestions: [
          "Which machine should I investigate first?",
          "Give me a summary of the factory.",
          "Which machine is wasting the most energy?"
        ]
      }
    ])
  }

  // ==========================================
  // Lifecycle & Polling
  // ==========================================

  useEffect(() => {
    fetchMachines()
    fetchTariffConfig()
    fetchLatestReadings()
    fetchEnergyOverview()
    fetchDiagnosisOverview()
    fetchHealthOverview()
    fetchQuickQuestions()
    fetchUnifiedEvents()

    const intervalId = setInterval(() => {
      fetchLatestReadings()
      fetchEnergyOverview()
      fetchDiagnosisOverview()
      fetchHealthOverview()
      fetchUnifiedEvents()
    }, 2000)

    return () => clearInterval(intervalId)
  }, [machines.length])

  // Machine Selection / Detail Handling
  const handleOpenMachineDetail = (machine) => {
    setSelectedMachine(machine)
    const machineId = machine.machine_id

    // Fetch baseline
    api.getMachineBaseline(machineId).then(data => setSelectedBaseline(data)).catch(() => {})

    // Fetch history
    api.getMachineReadings(machineId, 50).then(data => setSelectedHistory(Array.isArray(data) ? data.reverse() : [])).catch(() => {})

    // Fetch energy summary
    api.getMachineEnergySummary(machineId, 24).then(data => setSelectedEnergySummary(data)).catch(() => {})

    // Fetch diagnosis
    api.getMachineDiagnosis(machineId).then(data => setSelectedDiagnosis(data)).catch(() => {})

    // Fetch health
    api.getMachineHealth(machineId).then(data => setSelectedHealth(data)).catch(() => {})

    // Fetch timeline
    fetchMachineTimeline(machineId)
  }

  const handleCloseMachineDetail = () => {
    setSelectedMachine(null)
    setSelectedBaseline(null)
    setSelectedHistory([])
    setSelectedEnergySummary(null)
    setSelectedDiagnosis(null)
    setSelectedHealth(null)
    setTrainingStatus('idle')
    setTrainingMessage('')
  }

  const getMachineHealthStatus = (machineId) => {
    if (!healthOverview) return 'HEALTHY'
    const list = healthOverview.machines || healthOverview.ranked_machines || []
    const found = list.find(m => m.machine_id === machineId)
    return found ? found.health_status : 'HEALTHY'
  }

  const getMachinePriorityScore = (machineId) => {
    if (!healthOverview) return 0
    const list = healthOverview.machines || healthOverview.ranked_machines || []
    const found = list.find(m => m.machine_id === machineId)
    return found ? found.priority_score : 0
  }

  const formatTimestamp = (ts) => {
    if (!ts) return '-'
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return ts
    }
  }

  const renderStatusBadge = (status) => {
    const s = (status || 'HEALTHY').toUpperCase()
    let badgeClass = 'healthy'
    let label = 'Healthy'

    if (s === 'CRITICAL' || s === 'HIGH') {
      badgeClass = 'critical'
      label = 'Critical'
    } else if (s === 'ATTENTION' || s === 'MEDIUM') {
      badgeClass = 'attention'
      label = 'Attention'
    } else if (s === 'WATCH' || s === 'LOW') {
      badgeClass = 'watch'
      label = 'Watch'
    } else if (s === 'IDLE' || s === 'STOPPED') {
      badgeClass = 'idle'
      label = s === 'IDLE' ? 'Idle' : 'Stopped'
    }

    return (
      <span className={`status-badge ${badgeClass}`}>
        <span className={`status-dot ${badgeClass}`} />
        {label}
      </span>
    )
  }

  const renderOperatingStateBadge = (state) => {
    const s = (state || 'RUNNING').toUpperCase()
    let badgeClass = 'healthy'
    let label = 'Running'

    if (s === 'RUNNING') {
      badgeClass = 'healthy'
      label = 'Running'
    } else if (s === 'STARTING') {
      badgeClass = 'watch'
      label = 'Starting'
    } else if (s === 'IDLE') {
      badgeClass = 'idle'
      label = 'Idle'
    } else if (s === 'OFF' || s === 'STOPPED') {
      badgeClass = 'critical'
      label = 'Off'
    }

    return (
      <span className={`status-badge ${badgeClass}`}>
        <span className={`status-dot ${badgeClass}`} />
        {label}
      </span>
    )
  }

  // Sparkline Chart Renderer
  const renderTrendChart = (title, param, baselineMean, unit) => {
    if (!selectedHistory || selectedHistory.length === 0) return null

    const bMean = baselineMean || 0
    const vals = selectedHistory.map(r => r[param] ?? bMean)
    const minVal = Math.min(...vals, bMean) * 0.95
    const maxVal = Math.max(...vals, bMean) * 1.05
    const range = maxVal - minVal || 1.0

    const width = 450
    const height = 75

    const points = selectedHistory.map((r, i) => {
      const x = (i / Math.max(selectedHistory.length - 1, 1)) * width
      const y = height - (((r[param] ?? bMean) - minVal) / range) * height
      return `${x},${y}`
    }).join(" ")

    const baselineY = height - ((bMean - minVal) / range) * height
    const latestVal = vals[vals.length - 1]

    return (
      <div className="trend-chart-box" key={param}>
        <div className="chart-header">
          <span className="chart-title">{title}</span>
          <span className="chart-stats">
            Baseline: {safeNumber(bMean, 2, unit)} &bull; Recent: {safeNumber(latestVal, 2, unit)}
          </span>
        </div>
        <div style={{ position: 'relative', marginTop: '0.25rem' }}>
          <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
            <line 
              x1="0" 
              y1={baselineY} 
              x2={width} 
              y2={baselineY} 
              stroke="#CBD5E1" 
              strokeDasharray="4,4" 
              strokeWidth="1.5"
            />
            <polyline
              fill="none"
              stroke="#2563EB"
              strokeWidth="2"
              points={points}
            />
          </svg>
        </div>
      </div>
    )
  }

  // Filtered Machines
  const filteredMachines = machines.filter(m => {
    const matchesSearch = m.machine_id.toLowerCase().includes(machineSearch.toLowerCase()) ||
                          m.machine_name.toLowerCase().includes(machineSearch.toLowerCase())
    if (!matchesSearch) return false

    if (machineStatusFilter === 'ALL') return true
    const h = getMachineHealthStatus(m.machine_id)
    return h === machineStatusFilter
  })

  // Filtered Events
  const filteredEvents = unifiedEvents.filter(e => {
    if (eventFilter === 'ALL') return true
    return e.status === eventFilter
  })

  // Fleet Counts
  const totalCount = machines.length
  const healthyCount = healthOverview ? healthOverview.healthy_count : machines.length
  const attentionCount = healthOverview ? healthOverview.attention_count : 0
  const criticalCount = healthOverview ? healthOverview.critical_count : 0

  return (
    <div className="app-shell">
      {/* =========================================================================
          1. Left Sidebar Navigation
          ========================================================================= */}
      <aside className="app-sidebar">
        <div className="sidebar-header">
          <div className="brand-logo">
            <div className="brand-icon">G</div>
            <div className="brand-text">
              <span className="brand-name">GridLite</span>
              <span className="brand-subtitle">Industrial Intelligence</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button 
            className={`nav-item ${activeNav === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveNav('dashboard')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
            <span className="nav-label">Overview</span>
          </button>

          <button 
            className={`nav-item ${activeNav === 'machines' ? 'active' : ''}`}
            onClick={() => setActiveNav('machines')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
            <span className="nav-label">Machines</span>
          </button>

          <button 
            className={`nav-item ${activeNav === 'events' ? 'active' : ''}`}
            onClick={() => setActiveNav('events')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <span className="nav-label">Events</span>
            {unifiedEvents.filter(e => e.status === 'ACTIVE').length > 0 && (
              <span className="nav-badge">{unifiedEvents.filter(e => e.status === 'ACTIVE').length}</span>
            )}
          </button>

          <button 
            className={`nav-item ${activeNav === 'energy' ? 'active' : ''}`}
            onClick={() => setActiveNav('energy')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="nav-label">Energy</span>
          </button>

          <button 
            className={`nav-item ${activeNav === 'diagnosis' ? 'active' : ''}`}
            onClick={() => setActiveNav('diagnosis')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="nav-label">Diagnosis</span>
          </button>

          <button 
            className={`nav-item ${activeNav === 'assistant' ? 'active' : ''}`}
            onClick={() => setActiveNav('assistant')}
          >
            <svg className="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <span className="nav-label">AI Assistant</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="system-status-indicator">
            <span className={`status-dot-sm ${backendStatus === 'connected' ? 'online' : 'offline'}`} />
            <span>{backendStatus === 'connected' ? 'System operational' : 'Backend offline'}</span>
          </div>
        </div>
      </aside>

      {/* =========================================================================
          2. Main Application Area
          ========================================================================= */}
      <div className="app-main">
        {/* Top Header Bar */}
        <header className="top-bar">
          <div className="top-bar-title-group">
            <h1 className="top-bar-title">
              {activeNav === 'dashboard' && 'Operations Dashboard'}
              {activeNav === 'machines' && 'Machine Fleet'}
              {activeNav === 'events' && 'Event Timeline'}
              {activeNav === 'energy' && 'Energy Analytics'}
              {activeNav === 'diagnosis' && 'Fault Diagnosis'}
              {activeNav === 'assistant' && 'GridLite Assistant'}
            </h1>
            <span className="top-bar-subtitle">
              {activeNav === 'dashboard' && 'Real-time telemetry and plant health overview'}
              {activeNav === 'machines' && 'Monitor operating states and parameter baselines'}
              {activeNav === 'events' && 'Filterable operational alert feed'}
              {activeNav === 'energy' && 'Power baselines, excess consumption and cost tracking'}
              {activeNav === 'diagnosis' && 'Evidence-based diagnostic suggestions and inspections'}
              {activeNav === 'assistant' && 'Database-grounded operational queries and verification'}
            </span>
          </div>

          <div className="top-bar-actions">
            <span className="live-pill">
              <span className="pulse-dot" />
              Live
            </span>

            <button 
              className="btn btn-secondary btn-sm"
              onClick={handleResetDemo}
              disabled={isResettingDemo}
            >
              {isResettingDemo ? 'Resetting...' : 'Reset Demo'}
            </button>
          </div>
        </header>

        {/* Demo Reset Feedback Banner */}
        {demoResetMessage && (
          <div style={{ background: '#ECFDF5', borderBottom: '1px solid #A7F3D0', padding: '0.5rem 1.75rem', fontSize: '0.8rem', color: '#047857', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{demoResetMessage}</span>
            <button onClick={() => setDemoResetMessage('')} style={{ background: 'none', border: 'none', color: '#047857', cursor: 'pointer', fontWeight: 600 }}>&times;</button>
          </div>
        )}

        {/* =========================================================================
            3. Tab Content Router
            ========================================================================= */}
        <main className="content-container">
          {/* Render Cold Start & Connection Status Alert */}
          {backendStatus === 'offline' && machines.length === 0 && (
            <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: '8px', padding: '1rem 1.25rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <span className="pulse-dot" style={{ background: '#3B82F6', width: '10px', height: '10px', display: 'inline-block' }} />
                <div>
                  <div style={{ fontWeight: 600, color: '#1E3A8A', fontSize: '0.9rem' }}>Connecting to GridLite Backend...</div>
                  <div style={{ fontSize: '0.8rem', color: '#3B82F6', marginTop: '2px' }}>
                    Render cloud instance may take 15–30s to wake from sleep. Contacting {API_BASE_URL}
                  </div>
                </div>
              </div>
              <button 
                className="btn btn-secondary btn-sm" 
                onClick={fetchMachines}
                style={{ whiteSpace: 'nowrap' }}
              >
                Retry Connection
              </button>
            </div>
          )}

          {/* -----------------------------------------------------------------------
              TAB 1: DASHBOARD / OVERVIEW
              ----------------------------------------------------------------------- */}
          {activeNav === 'dashboard' && (
            <>
              {/* Fleet Summary Row */}
              <div className="grid-4">
                <div className="metric-card">
                  <span className="metric-label">Total Machines</span>
                  <span className="metric-value">{totalCount}</span>
                  <span className="metric-detail">Active edge nodes</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Healthy</span>
                  <span className="metric-value" style={{ color: 'var(--status-healthy-text)' }}>{healthyCount}</span>
                  <span className="metric-detail">Operating within baseline</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Attention Required</span>
                  <span className="metric-value" style={{ color: 'var(--status-attention-text)' }}>{attentionCount}</span>
                  <span className="metric-detail">Elevated deviation or drift</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Critical</span>
                  <span className="metric-value" style={{ color: 'var(--status-critical-text)' }}>{criticalCount}</span>
                  <span className="metric-detail">Immediate action recommended</span>
                </div>
              </div>

              {/* Priority Section: Machines Requiring Attention */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Machines Requiring Attention</h2>
                    <p className="card-subtitle">Prioritized ranking based on anomaly severity, behavioral shifts and energy loss</p>
                  </div>
                </div>
                <div className="table-container">
                  {healthOverview && (healthOverview.machines || healthOverview.ranked_machines) && (healthOverview.machines || healthOverview.ranked_machines).filter(m => m.health_status !== 'HEALTHY').length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Machine</th>
                          <th>Status</th>
                          <th>Priority Score</th>
                          <th>Primary Issue</th>
                          <th>Operator Action</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(healthOverview.machines || healthOverview.ranked_machines).filter(m => m.health_status !== 'HEALTHY').map(m => {
                          const machineObj = machines.find(item => item.machine_id === m.machine_id)
                          return (
                            <tr key={m.machine_id}>
                              <td>
                                <div className="machine-cell">
                                  <span className="machine-id-text" onClick={() => machineObj && handleOpenMachineDetail(machineObj)}>
                                    {m.machine_id}
                                  </span>
                                  <span className="machine-name-text">{m.machine_name}</span>
                                </div>
                              </td>
                              <td>{renderStatusBadge(m.health_status)}</td>
                              <td>
                                <span style={{ fontWeight: 700, color: m.priority_score > 70 ? 'var(--status-critical-text)' : 'var(--text-primary)' }}>
                                  {m.priority_score} / 100
                                </span>
                              </td>
                              <td style={{ maxWidth: '300px' }}>{m.primary_reason}</td>
                              <td>
                                <span className="status-badge idle">{m.operator_status}</span>
                              </td>
                              <td>
                                <button 
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => machineObj && handleOpenMachineDetail(machineObj)}
                                >
                                  Inspect
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-state-title">All Machines Normal</span>
                      <p className="empty-state-text">No active anomalies, significant behavioral drift or critical alerts detected across the fleet.</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Live Telemetry Table */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Live Telemetry</h2>
                    <p className="card-subtitle">Real-time parameter readings streamed from edge machine controllers</p>
                  </div>
                  <button className="btn btn-secondary btn-sm" onClick={() => setActiveNav('machines')}>
                    View All
                  </button>
                </div>
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Machine</th>
                        <th>Operating State</th>
                        <th>Health</th>
                        <th>Power</th>
                        <th>Temperature</th>
                        <th>Vibration</th>
                        <th>Power Factor</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {machines.map(m => {
                        const reading = latestReadings[m.machine_id]
                        const health = getMachineHealthStatus(m.machine_id)
                        return (
                          <tr key={m.machine_id}>
                            <td>
                              <div className="machine-cell">
                                <span className="machine-id-text" onClick={() => handleOpenMachineDetail(m)}>
                                  {m.machine_id}
                                </span>
                                <span className="machine-name-text">{m.machine_name} &bull; {m.location}</span>
                              </div>
                            </td>
                            <td>{renderOperatingStateBadge(reading ? reading.operating_state : 'RUNNING')}</td>
                            <td>{renderStatusBadge(health)}</td>
                            <td>{safeNumber(reading?.power, 2, ' kW')}</td>
                            <td>{safeNumber(reading?.temperature, 1, ' °C')}</td>
                            <td>{safeNumber(reading?.vibration, 3)}</td>
                            <td>{safeNumber(reading?.power_factor, 2)}</td>
                            <td>
                              <button 
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleOpenMachineDetail(m)}
                              >
                                Details
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Recent Events Section */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Recent Events</h2>
                    <p className="card-subtitle">Live event stream from unified event management pipeline</p>
                  </div>
                  <button className="btn btn-secondary btn-sm" onClick={() => setActiveNav('events')}>
                    View Event Feed
                  </button>
                </div>
                <div className="table-container">
                  {unifiedEvents.length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Machine</th>
                          <th>Event Type</th>
                          <th>Severity</th>
                          <th>Description</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {unifiedEvents.slice(0, 5).map(e => (
                          <tr key={e.id}>
                            <td>{formatTimestamp(e.timestamp)}</td>
                            <td style={{ fontWeight: 600 }}>{e.machine_id}</td>
                            <td>{e.event_type.replace(/_/g, ' ')}</td>
                            <td>{renderStatusBadge(e.severity)}</td>
                            <td style={{ maxWidth: '350px' }}>{e.title}</td>
                            <td>
                              <span className={`status-badge ${e.status === 'ACTIVE' ? 'critical' : e.status === 'ACKNOWLEDGED' ? 'watch' : 'healthy'}`}>
                                {e.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-state-title">No Recent Events</span>
                      <p className="empty-state-text">No operational alerts or state changes have been recorded recently.</p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* -----------------------------------------------------------------------
              TAB 2: MACHINES MANAGEMENT
              ----------------------------------------------------------------------- */}
          {activeNav === 'machines' && (
            <div className="card">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Machine Fleet</h2>
                  <p className="card-subtitle">Comprehensive operating parameters, health evaluations, and baseline tracking</p>
                </div>
                <div className="filter-bar">
                  <div className="search-input-wrapper">
                    <svg className="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input 
                      type="text" 
                      className="search-input" 
                      placeholder="Search machines..." 
                      value={machineSearch}
                      onChange={(e) => setMachineSearch(e.target.value)}
                    />
                  </div>

                  <div className="filter-pills">
                    {['ALL', 'HEALTHY', 'WATCH', 'ATTENTION', 'CRITICAL'].map(status => (
                      <button
                        key={status}
                        className={`filter-pill ${machineStatusFilter === status ? 'active' : ''}`}
                        onClick={() => setMachineStatusFilter(status)}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Machine ID</th>
                      <th>Machine Name</th>
                      <th>Type & Location</th>
                      <th>State</th>
                      <th>Health</th>
                      <th>Power</th>
                      <th>Temp</th>
                      <th>Vibration</th>
                      <th>Priority</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMachines.map(m => {
                      const reading = latestReadings[m.machine_id]
                      const health = getMachineHealthStatus(m.machine_id)
                      const priority = getMachinePriorityScore(m.machine_id)
                      return (
                        <tr key={m.machine_id}>
                          <td>
                            <span className="machine-id-text" onClick={() => handleOpenMachineDetail(m)}>
                              {m.machine_id}
                            </span>
                          </td>
                          <td>{m.machine_name}</td>
                          <td>{m.machine_type} &bull; {m.location}</td>
                          <td>{renderOperatingStateBadge(reading ? reading.operating_state : 'RUNNING')}</td>
                          <td>{renderStatusBadge(health)}</td>
                          <td>{safeNumber(reading?.power, 2, ' kW')}</td>
                          <td>{safeNumber(reading?.temperature, 1, ' °C')}</td>
                          <td>{safeNumber(reading?.vibration, 3)}</td>
                          <td>
                            <span style={{ fontWeight: 600 }}>{priority} / 100</span>
                          </td>
                          <td>
                            <button 
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleOpenMachineDetail(m)}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* -----------------------------------------------------------------------
              TAB 3: EVENTS FEED
              ----------------------------------------------------------------------- */}
          {activeNav === 'events' && (
            <div className="card">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Event Feed</h2>
                  <p className="card-subtitle">Real-time industrial notifications, state changes and anomaly events</p>
                </div>
                <div className="filter-pills">
                  {['ALL', 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'].map(st => (
                    <button
                      key={st}
                      className={`filter-pill ${eventFilter === st ? 'active' : ''}`}
                      onClick={() => setEventFilter(st)}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              <div className="table-container">
                {filteredEvents.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Machine</th>
                        <th>Event Type</th>
                        <th>Severity</th>
                        <th>Title & Description</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredEvents.map(e => (
                        <tr key={e.id}>
                          <td>{formatTimestamp(e.timestamp)}</td>
                          <td style={{ fontWeight: 600 }}>{e.machine_id}</td>
                          <td>{e.event_type.replace(/_/g, ' ')}</td>
                          <td>{renderStatusBadge(e.severity)}</td>
                          <td style={{ maxWidth: '400px' }}>
                            <div style={{ fontWeight: 600 }}>{e.title}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{e.description}</div>
                          </td>
                          <td>
                            <span className={`status-badge ${e.status === 'ACTIVE' ? 'critical' : e.status === 'ACKNOWLEDGED' ? 'watch' : 'healthy'}`}>
                              {e.status}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: '0.4rem' }}>
                              {e.status === 'ACTIVE' && (
                                <button 
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => handleAcknowledgeEvent(e.id)}
                                >
                                  Acknowledge
                                </button>
                              )}
                              {e.status !== 'RESOLVED' && (
                                <button 
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => handleResolveEvent(e.id)}
                                >
                                  Resolve
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-state">
                    <span className="empty-state-title">No Events Found</span>
                    <p className="empty-state-text">No events match the selected status filter.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* -----------------------------------------------------------------------
              TAB 4: ENERGY INTELLIGENCE
              ----------------------------------------------------------------------- */}
          {activeNav === 'energy' && (
            <>
              {/* Top Energy Metrics */}
              <div className="grid-4">
                <div className="metric-card">
                  <span className="metric-label">Total Consumption (24h)</span>
                  <span className="metric-value">{safeNumber(energyOverview?.total_energy_kwh, 1, ' kWh')}</span>
                  <span className="metric-detail">Active plant baseline</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Expected Consumption</span>
                  <span className="metric-value" style={{ color: 'var(--text-secondary)' }}>
                    {safeNumber(energyOverview?.expected_energy_kwh, 1, ' kWh')}
                  </span>
                  <span className="metric-detail">Theoretical physics profile</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Excess Consumption</span>
                  <span className="metric-value" style={{ color: (energyOverview?.excess_energy_kwh || 0) > 0 ? 'var(--status-critical-text)' : 'var(--status-healthy-text)' }}>
                    {safeNumber(energyOverview?.excess_energy_kwh, 1, ' kWh')}
                  </span>
                  <span className="metric-detail">Delta above normal operation</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Estimated Excess Cost</span>
                  <span className="metric-value" style={{ color: (energyOverview?.estimated_excess_cost || 0) > 0 ? 'var(--status-attention-text)' : 'var(--status-healthy-text)' }}>
                    ₹{safeNumber(energyOverview?.estimated_excess_cost, 2)}
                  </span>
                  <span className="metric-detail">Calculated at ₹{tariff}/kWh</span>
                </div>
              </div>

              {/* Tariff Configuration Card */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Electricity Tariff Configuration</h2>
                    <p className="card-subtitle">Set commercial power rate for financial penalty estimation</p>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>₹ / kWh:</span>
                      <input 
                        type="number" 
                        step="0.5" 
                        min="0" 
                        value={inputTariff} 
                        onChange={(e) => setInputTariff(e.target.value)}
                        style={{ width: '80px', padding: '0.3rem 0.5rem', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}
                      />
                    </div>
                    <button className="btn btn-primary btn-sm" onClick={handleUpdateTariff}>
                      Save Rate
                    </button>
                  </div>
                </div>
              </div>

              {/* Energy Breakdown Table */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Energy Consumption by Machine</h2>
                    <p className="card-subtitle">Real-time comparison between actual power draw and baseline profile</p>
                  </div>
                </div>
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Machine</th>
                        <th>Current Power</th>
                        <th>Expected Power</th>
                        <th>Difference (%)</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {machines.map(m => {
                        const reading = latestReadings[m.machine_id]
                        const energy = machinesEnergy[m.machine_id]
                        const curPwr = reading?.power ?? energy?.current_power_kw ?? 0
                        const expPwr = energy?.baseline_power_kw ?? energy?.expected_power ?? curPwr
                        const diffPct = energy?.difference_percentage ?? (expPwr > 0 ? ((curPwr - expPwr) / expPwr) * 100 : 0)
                        const isInefficient = diffPct >= 20.0 || energy?.energy_status === 'HIGH_CONSUMPTION'

                        return (
                          <tr key={m.machine_id}>
                            <td>
                              <div className="machine-cell">
                                <span className="machine-id-text" onClick={() => handleOpenMachineDetail(m)}>
                                  {m.machine_id}
                                </span>
                                <span className="machine-name-text">{m.machine_name}</span>
                              </div>
                            </td>
                            <td>{safeNumber(curPwr, 2, ' kW')}</td>
                            <td>{safeNumber(expPwr, 2, ' kW')}</td>
                            <td>
                              <span style={{ fontWeight: 600, color: isInefficient ? 'var(--status-critical-text)' : diffPct > 10 ? 'var(--status-attention-text)' : 'var(--text-primary)' }}>
                                {diffPct > 0 ? `+${safeNumber(diffPct, 1, '%')}` : safeNumber(diffPct, 1, '%')}
                              </span>
                            </td>
                            <td>
                              <span className={`status-badge ${isInefficient ? 'critical' : diffPct > 10 ? 'watch' : 'healthy'}`}>
                                {isInefficient ? 'Inefficient' : diffPct > 10 ? 'Elevated' : 'Optimal'}
                              </span>
                            </td>
                            <td>
                              <button 
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleOpenMachineDetail(m)}
                              >
                                24h Summary
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* -----------------------------------------------------------------------
              TAB 5: FAULT DIAGNOSIS
              ----------------------------------------------------------------------- */}
          {activeNav === 'diagnosis' && (
            <>
              <div className="engineering-disclaimer">
                <strong>Engineering Notice:</strong> Diagnostic suggestions are based on observed telemetry deviations and baseline comparisons. Hypotheses must be verified by qualified plant personnel prior to physical maintenance.
              </div>

              <div className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Active Diagnostic Hypotheses</h2>
                    <p className="card-subtitle">Automated root cause identification with verifiable sensor evidence</p>
                  </div>
                </div>

                <div className="table-container">
                  {diagnosisOverview && diagnosisOverview.events && diagnosisOverview.events.length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Machine</th>
                          <th>Possible Condition</th>
                          <th>Evidence Score</th>
                          <th>Status</th>
                          <th>Operator Review</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diagnosisOverview.events.map(ev => {
                          const machineObj = machines.find(m => m.machine_id === ev.machine_id)
                          return (
                            <tr key={ev.id}>
                              <td>
                                <div className="machine-cell">
                                  <span className="machine-id-text" onClick={() => machineObj && handleOpenMachineDetail(machineObj)}>
                                    {ev.machine_id}
                                  </span>
                                  <span className="machine-name-text">{ev.machine_name}</span>
                                </div>
                              </td>
                              <td style={{ fontWeight: 600 }}>{ev.primary_cause.replace(/_/g, ' ')}</td>
                              <td>
                                <span style={{ fontWeight: 700 }}>
                                  {safeNumber((ev.evidence_score || 0) * 100, 0, '%')}
                                </span>
                              </td>
                              <td>
                                <span className="status-badge critical">{ev.status}</span>
                              </td>
                              <td>
                                <span className="status-badge idle">{ev.review_status}</span>
                              </td>
                              <td>
                                <button 
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => machineObj && handleOpenMachineDetail(machineObj)}
                                >
                                  Review Evidence
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-state-title">No Active Fault Hypotheses</span>
                      <p className="empty-state-text">No machines currently display compounding deviations that trigger diagnostic hypotheses.</p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* -----------------------------------------------------------------------
              TAB 6: AI ASSISTANT
              ----------------------------------------------------------------------- */}
          {activeNav === 'assistant' && (
            <div className="assistant-page">
              <div className="quick-questions-row">
                {(quickQuestions && quickQuestions.length > 0 ? quickQuestions : [
                  { label: "Factory Summary", query: "Give me a summary of the factory." },
                  { label: "Top Priority", query: "Which machine should I investigate first?" },
                  { label: "Energy Waste", query: "Which machine is wasting the most energy?" },
                  { label: "Why MOTOR-01 Critical?", query: "Why is MOTOR-01 critical?" }
                ]).map((q, idx) => {
                  const queryText = getQuestionText(q)
                  const labelText = getQuestionLabel(q)
                  return (
                    <button
                      key={idx}
                      className="quick-question-btn"
                      onClick={() => handleSendAssistantMessage(queryText)}
                    >
                      {labelText}
                    </button>
                  )
                })}
              </div>

              <div className="chat-container">
                <div className="chat-messages">
                  {assistantMessages.map(msg => (
                    <div key={msg.id} className={`chat-message ${msg.sender}`}>
                      <div className="message-bubble">
                        {msg.text}

                        {/* Evidence Table (Expandable) */}
                        {msg.evidence && msg.evidence.length > 0 && (
                          <div style={{ marginTop: '0.75rem' }}>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => setExpandedEvidenceMap(prev => ({ ...prev, [msg.id]: !prev[msg.id] }))}
                              style={{ fontSize: '0.72rem' }}
                            >
                              {expandedEvidenceMap[msg.id] ? 'Hide Evidence Table' : `View Verified Evidence (${msg.evidence.length} items)`}
                            </button>

                            {expandedEvidenceMap[msg.id] && (
                              <div className="evidence-table-container">
                                <table className="data-table" style={{ fontSize: '0.75rem' }}>
                                  <thead>
                                    <tr>
                                      <th>Parameter</th>
                                      <th>Current</th>
                                      <th>Baseline</th>
                                      <th>Deviation</th>
                                      <th>Source</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {msg.evidence.map((ev, idx) => (
                                      <tr key={idx}>
                                        <td style={{ fontWeight: 600 }}>{ev.parameter}</td>
                                        <td>{safeNumber(ev.observed_value, 2, ` ${ev.unit || ''}`)}</td>
                                        <td>{safeNumber(ev.baseline_reference, 2, ` ${ev.unit || ''}`)}</td>
                                        <td>
                                          {ev.deviation_percentage !== null && ev.deviation_percentage !== undefined ? `${ev.deviation_percentage > 0 ? '+' : ''}${safeNumber(ev.deviation_percentage, 1, '%')}` : '-'}
                                        </td>
                                        <td style={{ color: 'var(--text-muted)' }}>{ev.source_module || 'Pipeline'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Suggestions */}
                        {msg.suggestions && msg.suggestions.length > 0 && (
                          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                            {msg.suggestions.map((sug, i) => {
                              const sugText = getQuestionText(sug)
                              const sugLabel = getQuestionLabel(sug)
                              return (
                                <button
                                  key={i}
                                  className="quick-question-btn"
                                  onClick={() => handleSendAssistantMessage(sugText)}
                                  style={{ fontSize: '0.7rem' }}
                                >
                                  {sugLabel}
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </div>

                      <div className="message-meta">
                        <span>{msg.sender === 'user' ? 'Operator' : 'GridLite Assistant'}</span>
                        {msg.sender === 'assistant' && <span>&bull; Grounded in SQLite Telemetry</span>}
                      </div>
                    </div>
                  ))}

                  {isAssistantLoading && (
                    <div className="chat-message assistant">
                      <div className="message-bubble" style={{ color: 'var(--text-muted)' }}>
                        Querying verified telemetry database...
                      </div>
                    </div>
                  )}
                </div>

                <div className="chat-input-area">
                  <input
                    type="text"
                    className="chat-input"
                    placeholder="Ask about machine status, anomalies, baselines or energy..."
                    value={assistantInput}
                    onChange={(e) => setAssistantInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSendAssistantMessage()
                    }}
                  />
                  <button 
                    className="btn btn-primary"
                    onClick={() => handleSendAssistantMessage()}
                    disabled={isAssistantLoading}
                  >
                    Send
                  </button>
                  <button 
                    className="btn btn-secondary"
                    onClick={handleClearConversation}
                    title="Clear Conversation History"
                  >
                    Clear
                  </button>
                </div>
              </div>
            </div>
          )}

        </main>
      </div>

      {/* =========================================================================
          4. Machine Detail Modal (Inspection Drawer)
          ========================================================================= */}
      {selectedMachine && (
        <div className="modal-overlay" onClick={handleCloseMachineDetail}>
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-header-info">
                <div>
                  <h2 className="modal-title">{selectedMachine.machine_id} &bull; {selectedMachine.machine_name}</h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                    {selectedMachine.machine_type} &bull; Location: {selectedMachine.location}
                  </p>
                </div>
                {renderStatusBadge(getMachineHealthStatus(selectedMachine.machine_id))}
              </div>
              <button 
                className="btn-icon" 
                onClick={handleCloseMachineDetail}
                style={{ fontSize: '1.25rem', lineHeight: 1, padding: '0.2rem 0.5rem' }}
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {/* Telemetry Grid */}
              <div className="section-block">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="section-title">Current Telemetry</span>
                  <button 
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTrainModel(selectedMachine.machine_id)}
                    disabled={trainingStatus === 'training'}
                  >
                    {trainingStatus === 'training' ? 'Retraining...' : 'Retrain ML Model'}
                  </button>
                </div>

                {trainingMessage && (
                  <div style={{ fontSize: '0.75rem', padding: '0.4rem 0.75rem', borderRadius: 'var(--radius-sm)', background: trainingStatus === 'error' ? 'var(--status-critical-bg)' : 'var(--status-healthy-bg)', color: trainingStatus === 'error' ? 'var(--status-critical-text)' : 'var(--status-healthy-text)', border: `1px solid ${trainingStatus === 'error' ? 'var(--status-critical-border)' : 'var(--status-healthy-border)'}` }}>
                    {trainingMessage}
                  </div>
                )}

                {(() => {
                  const r = latestReadings[selectedMachine.machine_id]
                  return (
                    <div className="telemetry-grid">
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Power</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.power, 2, ' kW')}</div>
                      </div>
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Temperature</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.temperature, 1, ' °C')}</div>
                      </div>
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Vibration</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.vibration, 3)}</div>
                      </div>
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Current</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.current, 2, ' A')}</div>
                      </div>
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Voltage</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.voltage, 1, ' V')}</div>
                      </div>
                      <div className="telemetry-tile">
                        <span className="telemetry-tile-label">Power Factor</span>
                        <div className="telemetry-tile-value">{safeNumber(r?.power_factor, 2)}</div>
                      </div>
                    </div>
                  )
                })()}
              </div>

              {/* Health & Priority Breakdown */}
              {selectedHealth && (
                <div className="section-block">
                  <span className="section-title">Health & Priority Assessment</span>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem' }}>
                    <div className="metric-card">
                      <span className="metric-label">Priority Score</span>
                      <span className="metric-value" style={{ color: selectedHealth.priority_score > 70 ? 'var(--status-critical-text)' : 'var(--text-primary)' }}>
                        {selectedHealth.priority_score} / 100
                      </span>
                      <span className="metric-detail">Status: {selectedHealth.health_status}</span>
                    </div>

                    <div className="card" style={{ padding: '0.85rem' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Primary Assessment Reason</span>
                      <p style={{ fontSize: '0.85rem', marginTop: '0.25rem', color: 'var(--text-primary)' }}>{selectedHealth.primary_reason}</p>
                      
                      <div style={{ marginTop: '0.65rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Operator Review:</span>
                        <button 
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleHealthOperatorStatus('UNDER_REVIEW')}
                          disabled={isUpdatingOperatorStatus}
                        >
                          Mark Under Review
                        </button>
                        <button 
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleHealthOperatorStatus('RESOLVED')}
                          disabled={isUpdatingOperatorStatus}
                        >
                          Mark Resolved
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Behavioral Changes Table */}
              <div className="section-block">
                <span className="section-title">Behavioral Drift vs Baseline</span>
                <div className="table-container">
                  {allChanges.filter(c => c.machine_id === selectedMachine.machine_id).length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Parameter</th>
                          <th>Established Baseline</th>
                          <th>Recent Value</th>
                          <th>Percentage Shift</th>
                          <th>Persistence Count</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allChanges.filter(c => c.machine_id === selectedMachine.machine_id).map(c => (
                          <tr key={c.id}>
                            <td style={{ fontWeight: 600 }}>{c.parameter}</td>
                            <td>{safeNumber(c.baseline_value, 2)}</td>
                            <td>{safeNumber(c.recent_value, 2)}</td>
                            <td style={{ color: (c.percentage_change || 0) > 0 ? 'var(--status-critical-text)' : 'var(--status-healthy-text)', fontWeight: 600 }}>
                              {(c.percentage_change || 0) > 0 ? `+${safeNumber(c.percentage_change, 1, '%')}` : safeNumber(c.percentage_change, 1, '%')}
                            </td>
                            <td>{c.persistence_count} samples</td>
                            <td>
                              <span className="status-badge critical">{c.status}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      No significant behavioral deviations from learned baseline.
                    </div>
                  )}
                </div>
              </div>

              {/* Diagnosis & Suggested Inspections */}
              {selectedDiagnosis && selectedDiagnosis.status === 'DIAGNOSIS_AVAILABLE' && (
                <div className="section-block">
                  <span className="section-title">Diagnostic Hypotheses & Inspections</span>
                  <div className="card" style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Possible Condition</span>
                        <h4 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.1rem' }}>
                          {selectedDiagnosis.primary_cause ? selectedDiagnosis.primary_cause.replace(/_/g, ' ') : '-'}
                        </h4>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Evidence Confidence</span>
                        <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--primary)' }}>
                          {safeNumber((selectedDiagnosis.evidence_score || 0) * 100, 0, '%')}
                        </div>
                      </div>
                    </div>

                    {selectedDiagnosis.suggested_inspections && selectedDiagnosis.suggested_inspections.length > 0 && (
                      <div style={{ marginTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.65rem' }}>
                        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Suggested Inspections:</span>
                        <ul style={{ margin: '0.35rem 0 0 1.25rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {selectedDiagnosis.suggested_inspections.map((ins, idx) => (
                            <li key={idx} style={{ marginBottom: '0.2rem' }}>{ins}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div style={{ marginTop: '0.85rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Human Review:</span>
                      <button 
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleOperatorReview('ACCEPTED')}
                        disabled={isUpdatingReview}
                      >
                        Accept Hypothesis
                      </button>
                      <button 
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleOperatorReview('REJECTED')}
                        disabled={isUpdatingReview}
                      >
                        Reject
                      </button>
                      <button 
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleOperatorReview('RESOLVED')}
                        disabled={isUpdatingReview}
                      >
                        Mark Resolved
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Trend Charts */}
              {selectedBaseline && selectedHistory.length > 0 && (
                <div className="section-block">
                  <span className="section-title">Telemetry Parameter Trends (Last 50 Readings)</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {selectedBaseline.power && renderTrendChart('Power Trend', 'power', selectedBaseline.power.mean, ' kW')}
                    {selectedBaseline.temperature && renderTrendChart('Temperature Trend', 'temperature', selectedBaseline.temperature.mean, ' °C')}
                    {selectedBaseline.vibration && renderTrendChart('Vibration Trend', 'vibration', selectedBaseline.vibration.mean, '')}
                  </div>
                </div>
              )}

              {/* Event Timeline */}
              <div className="section-block">
                <span className="section-title">Machine Event History</span>
                <div className="table-container">
                  {machineTimeline.length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Event Type</th>
                          <th>Severity</th>
                          <th>Details</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {machineTimeline.map(e => (
                          <tr key={e.id}>
                            <td>{formatTimestamp(e.timestamp)}</td>
                            <td>{e.event_type.replace(/_/g, ' ')}</td>
                            <td>{renderStatusBadge(e.severity)}</td>
                            <td>{e.title}</td>
                            <td>
                              <span className={`status-badge ${e.status === 'ACTIVE' ? 'critical' : e.status === 'ACKNOWLEDGED' ? 'watch' : 'healthy'}`}>
                                {e.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      No events recorded for this machine.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
