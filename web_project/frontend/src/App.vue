<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ActionCard from './components/ActionCard.vue'
import HeroSection from './components/HeroSection.vue'
import HistoryCard from './components/HistoryCard.vue'
import LayoutDetailsCard from './components/LayoutDetailsCard.vue'
import LogCard from './components/LogCard.vue'
import MetaCard from './components/MetaCard.vue'
import ModeCard from './components/ModeCard.vue'
import OutputCard from './components/OutputCard.vue'
import PageTextCard from './components/PageTextCard.vue'
import PromptCard from './components/PromptCard.vue'
import UploadCard from './components/UploadCard.vue'
import VisualPreviewCard from './components/VisualPreviewCard.vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

const selectedMode = ref('gundam')
const availableModes = ref({})
const defaultPrompt = ref('')
const prompt = ref('')
const selectedFile = ref(null)
const previewUrl = ref('')
const isRunning = ref(false)
const serviceOnline = ref(false)
const loadError = ref('')
const inferenceResult = ref(null)
const activityLog = ref([])
const lastRunAt = ref('')
const isFetchingModes = ref(false)
const errorMessage = ref('')
const uploadLimitMb = ref(Number(import.meta.env.VITE_MAX_IMAGE_MB || 15))
const previewMode = ref('image')
const layoutItems = ref([])
const activeRegionKey = ref('')
const imageNaturalSize = ref({ width: 0, height: 0 })
const uploadType = ref('image')
const pageResults = ref([])
const activePageIndex = ref(0)
const historyItems = ref([])
const historyError = ref('')
const isLoadingHistory = ref(false)
const isHistoryView = ref(false)
const historyPreviewUrl = ref('')
const selectedHistoryId = ref('')
const regionOutputView = ref('raw')

// 进度相关
const progressInfo = ref({
  stage: '',
  percent: 0,
  message: '',
  current: 0,
  total: 100,
})
const progressEventSource = ref(null)

const modeCards = computed(() =>
  Object.entries(availableModes.value).map(([key, meta]) => ({
    key,
    ...meta,
    isActive: key === selectedMode.value,
  }))
)

const hasImage = computed(() => Boolean(selectedFile.value) || Boolean(historyPreviewUrl.value))
const canRun = computed(
  () => hasImage.value && Boolean(selectedMode.value) && !isRunning.value && !isHistoryView.value
)
const uploadLimitLabel = computed(() =>
  uploadLimitMb.value ? uploadLimitMb.value.toFixed(1) : '15'
)
const isPdfUpload = computed(() => uploadType.value === 'pdf')
const hasPages = computed(() => pageResults.value.length > 0)
const currentPage = computed(() => pageResults.value[activePageIndex.value] || null)
const previewImageSrc = computed(() => {
  if (historyPreviewUrl.value) {
    return historyPreviewUrl.value
  }
  if (currentPage.value?.imageData) {
    return currentPage.value.imageData
  }
  if (!isPdfUpload.value) {
    return previewUrl.value
  }
  return ''
})
const currentPageCleanText = computed(() => stripSpecialTags(currentPage.value?.text || ''))
const hasLayout = computed(() => layoutItems.value.length > 0)
const layoutRegions = computed(() =>
  layoutItems.value.flatMap((item) =>
    (item.boxes || []).map((box) => ({
      key: `${item.id}::${box.index}`,
      label: item.label,
      snippet: item.snippet || '',
      box,
    }))
  )
)
const selectedRegion = computed(() =>
  layoutRegions.value.find((region) => region.key === activeRegionKey.value) || null
)
const selectedRegionSnippet = computed(() => {
  if (selectedRegion.value?.snippet) {
    return selectedRegion.value.snippet
  }
  if (selectedRegion.value?.label === 'image') {
    return '该区域包含图像内容，可在原图中查看。'
  }
  return inferenceResult.value?.text || ''
})
const aspectRatioStyle = computed(() => {
  const { width, height } = imageNaturalSize.value
  if (width && height) {
    return `${width} / ${height}`
  }
  return '4 / 3'
})

const workflowSteps = computed(() => {
  const inferDone = Boolean(inferenceResult.value)
  return [
    {
      key: 'upload',
      label: '上传图片',
      description: 'PNG / JPG / JPEG',
      status: hasImage.value ? 'done' : 'active',
    },
    {
      key: 'mode',
      label: '选择模式',
      description: 'Tiny / Small / Base / Gundam',
      status: hasImage.value ? (inferDone ? 'done' : 'active') : 'pending',
    },
    {
      key: 'infer',
      label: '推理输出',
      description: 'DeepSeek-OCR',
      status: isRunning.value ? 'active' : inferDone ? 'done' : 'pending',
    },
  ]
})

const lastDuration = computed(() =>
  inferenceResult.value ? `${inferenceResult.value.durationMs.toFixed(0)} ms` : '--'
)

const regionHasHtmlTable = computed(() => /<table[\s>]/i.test(selectedRegionSnippet.value || ''))
const regionHtmlTableOutput = computed(() => extractTablesAsHtml(selectedRegionSnippet.value || ''))
const regionMarkdownTableOutput = computed(() => convertTablesToMarkdown(selectedRegionSnippet.value || ''))

function pushLog(message) {
  activityLog.value = [
    {
      id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
      message,
      timestamp: new Date().toLocaleTimeString(),
    },
    ...activityLog.value,
  ].slice(0, 6)
}

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return '--'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function handleFileChange(event) {
  const files = event.target.files
  if (!files?.length) return
  attachFile(files[0])
}

function attachFile(file, { source = 'upload' } = {}) {
  if (!file) return

  const limitBytes = uploadLimitMb.value ? uploadLimitMb.value * 1024 * 1024 : Infinity
  if (file.size > limitBytes) {
    errorMessage.value = `文件大小超过限制：${uploadLimitLabel.value} MB`
    pushLog('文件大小超出限制，未进行上传')
    return
  }

  selectedFile.value = file
  isHistoryView.value = false
  historyPreviewUrl.value = ''
  selectedHistoryId.value = ''
  inferenceResult.value = null
  lastRunAt.value = ''
  errorMessage.value = ''
  pageResults.value = []
  activePageIndex.value = 0
  uploadType.value = file.type === 'application/pdf' || file.name?.toLowerCase().endsWith('.pdf') ? 'pdf' : 'image'
  resetLayoutState()

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = URL.createObjectURL(file)
  const label = file.name || '剪贴板文件'
  pushLog(`${source === 'paste' ? '已粘贴文件' : '图片已就绪'}：${label}`)
}

function clearImage() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  selectedFile.value = null
  previewUrl.value = ''
  historyPreviewUrl.value = ''
  inferenceResult.value = null
  pageResults.value = []
  activePageIndex.value = 0
  uploadType.value = 'image'
  isHistoryView.value = false
  selectedHistoryId.value = ''
  resetLayoutState()
}

function handleDrop(event) {
  event.preventDefault()
  if (event.dataTransfer?.files?.length) {
    attachFile(event.dataTransfer.files[0])
  }
}

function handleDragOver(event) {
  event.preventDefault()
}

function handlePaste(event) {
  const items = event.clipboardData?.items || []
  const fileItem = Array.from(items).find((item) => item.kind === 'file')
  if (!fileItem) return

  const file = fileItem.getAsFile()
  if (!file) return

  attachFile(file, { source: 'paste' })
  event.preventDefault()
}

function extractTablesAsHtml(html) {
  if (!html || !/<table[\s>]/i.test(html)) return ''
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    doc.querySelectorAll('script, style').forEach((el) => el.remove())
    const tables = Array.from(doc.querySelectorAll('table'))
    if (!tables.length) return ''
    return tables.map((table) => table.outerHTML).join('\n')
  } catch (error) {
    console.warn('解析表格 HTML 失败', error)
    return ''
  }
}

function tableToMarkdown(tableElement) {
  const rows = Array.from(tableElement.querySelectorAll('tr')).map((row) =>
    Array.from(row.querySelectorAll('th, td')).map((cell) =>
      cell.textContent.trim().replace(/\|/g, '\\|')
    )
  )
  if (!rows.length) return ''

  const headerRow = rows.find((r, idx) => tableElement.querySelectorAll('tr')[idx]?.querySelector('th')) || rows[0]
  const headerIndex = rows.indexOf(headerRow)
  const bodyRows = rows.filter((_, idx) => idx !== headerIndex)
  const headerLine = `| ${headerRow.join(' | ')} |`
  const dividerLine = `| ${headerRow.map(() => '---').join(' | ')} |`
  const bodyLines = bodyRows.length
    ? bodyRows.map((r) => `| ${r.map((cell) => cell || ' ').join(' | ')} |`)
    : [`| ${headerRow.map(() => ' ').join(' | ')} |`]
  return [headerLine, dividerLine, ...bodyLines].join('\n')
}

function convertTablesToMarkdown(html) {
  if (!html || !/<table[\s>]/i.test(html)) return ''
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    doc.querySelectorAll('script, style').forEach((el) => el.remove())
    const tables = Array.from(doc.querySelectorAll('table'))
    if (!tables.length) return ''
    return tables
      .map((table) => tableToMarkdown(table))
      .filter(Boolean)
      .join('\n\n')
  } catch (error) {
    console.warn('转换 Markdown 表格失败', error)
    return ''
  }
}

function clamp01(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0
  return Math.min(1, Math.max(0, value))
}

function stripSpecialTags(text = '') {
  return text
    .replace(/<\|ref\|>[\s\S]*?<\|\/ref\|>/g, '')
    .replace(/<\|det\|>[\s\S]*?<\|\/det\|>/g, '')
    .replace(/<\|[^>]+?\|>/g, '')
    .trim()
}

function boxPercentStyle(box) {
  const normalized = Array.isArray(box.normalized) ? box.normalized : [0, 0, 0, 0]
  const [x1 = 0, y1 = 0, x2 = 0, y2 = 0] = normalized
  const left = clamp01(x1) * 100
  const top = clamp01(y1) * 100
  const widthPercent = Math.max(clamp01(x2) - clamp01(x1), 0.005) * 100
  const heightPercent = Math.max(clamp01(y2) - clamp01(y1), 0.005) * 100
  return {
    left: `${left}%`,
    top: `${top}%`,
    width: `${widthPercent}%`,
    height: `${heightPercent}%`,
  }
}

function resetLayoutState() {
  layoutItems.value = []
  previewMode.value = 'image'
  activeRegionKey.value = ''
  imageNaturalSize.value = { width: 0, height: 0 }
}

function applyLayoutFromPage(page) {
  if (!page?.layout?.items?.length) {
    resetLayoutState()
    return
  }

  const width = Number(page.layout.width) || imageNaturalSize.value.width || 1
  const height = Number(page.layout.height) || imageNaturalSize.value.height || 1
  imageNaturalSize.value = { width, height }

  const validItems = page.layout.items
    .filter((item) => Array.isArray(item.boxes) && item.boxes.length)
    .map((item, idx) => ({
      ...item,
      id: item.id || `item-${idx}`,
      boxes: item.boxes.map((box, boxIndex) => ({
        index: typeof box.index === 'number' ? box.index : boxIndex,
        normalized: box.normalized || box.norm || [0, 0, 0, 0],
        absolute: box.absolute || box.abs || [0, 0, 0, 0],
      })),
    }))

  if (!validItems.length) {
    resetLayoutState()
    return
  }

  const sanitizedText = stripSpecialTags(page.text || '')
  const textBlocks = sanitizedText
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)

  let cursor = 0
  layoutItems.value = validItems.map((item) => {
    let snippet = ''
    if (item.label !== 'image' && cursor < textBlocks.length) {
      snippet = textBlocks[cursor++]
    }
    return { ...item, snippet }
  })

  nextTick(() => {
    activeRegionKey.value = layoutRegions.value[0]?.key || ''
  })
  previewMode.value = 'layout'
}

function setPreviewMode(mode) {
  if ((mode === 'layout' || mode === 'clean') && !hasLayout.value) {
    return
  }
  previewMode.value = mode
}

function handleRegionSelect(regionKey) {
  activeRegionKey.value = regionKey
}

async function copySelectedRegion() {
  const snippet = selectedRegionSnippet.value?.trim()
  if (!snippet) return
  let content = snippet
  if (regionOutputView.value === 'html' && regionHtmlTableOutput.value) {
    content = regionHtmlTableOutput.value
  } else if (regionOutputView.value === 'markdown' && regionMarkdownTableOutput.value) {
    content = regionMarkdownTableOutput.value
  }
  await navigator.clipboard.writeText(content)
  pushLog('已复制所选区域文本')
}

async function copyCurrentPageText() {
  if (!currentPageCleanText.value) return
  await navigator.clipboard.writeText(currentPageCleanText.value)
  pushLog(`已复制第 ${activePageIndex.value + 1} 页文本`)
}

async function fetchHistory() {
  isLoadingHistory.value = true
  historyError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/api/history`)
    if (!response.ok) throw new Error('无法获取历史记录')
    const payload = await response.json()
    historyItems.value = payload.items || []
  } catch (error) {
    historyError.value = error.message || '获取历史记录失败'
  } finally {
    isLoadingHistory.value = false
  }
}

function applyResultPayload(payload, { fromHistory = false } = {}) {
  if (!payload) return

  const normalizedPages = Array.isArray(payload.pages) && payload.pages.length
    ? payload.pages
    : [
        {
          pageIndex: 0,
          text: payload.text,
          rawText: payload.rawText,
          layout: payload.layout,
          imageData: null,
        },
      ]

  inferenceResult.value = payload
  pageResults.value = normalizedPages
  activePageIndex.value = 0
  lastRunAt.value = payload.createdAt || new Date().toLocaleString()
  historyPreviewUrl.value = normalizedPages[0]?.imageData || ''
  selectedHistoryId.value = payload.historyId || ''
  uploadType.value = payload.isPdf ? 'pdf' : 'image'
  isHistoryView.value = fromHistory
  errorMessage.value = ''
  progressInfo.value = {
    stage: 'complete',
    percent: 100,
    message: fromHistory ? '历史结果已加载' : '识别完成！',
    current: 100,
    total: 100,
  }

  if (fromHistory) {
    selectedFile.value = {
      name: payload.fileName,
      size: payload.fileSize,
      lastModified: Date.parse(payload.createdAt) || Date.now(),
      history: true,
    }
    previewUrl.value = historyPreviewUrl.value
  }
}

async function loadHistory(historyId) {
  if (!historyId) return
  isLoadingHistory.value = true
  historyError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/api/history/${historyId}`)
    if (!response.ok) throw new Error('无法加载历史记录')
    const payload = await response.json()
    applyResultPayload(payload, { fromHistory: true })
    pushLog(`已打开历史记录：${payload.fileName || historyId}`)
  } catch (error) {
    historyError.value = error.message || '加载历史记录失败'
  } finally {
    isLoadingHistory.value = false
  }
}

async function downloadMarkdown() {
  if (!inferenceResult.value?.text) return

  const historyId = selectedHistoryId.value || inferenceResult.value?.historyId
  const fallbackName = inferenceResult.value?.fileName || 'ocr-result'
  const downloadBase = fallbackName.replace(/\.[^/.]+$/, '') || 'ocr-result'

  try {
    let blob
    if (historyId) {
      const response = await fetch(`${API_BASE_URL}/api/history/${historyId}/download?format=md`)
      if (!response.ok) throw new Error('下载失败')
      blob = await response.blob()
    } else {
      blob = new Blob([inferenceResult.value.text], {
        type: 'text/markdown;charset=utf-8',
      })
    }

    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${downloadBase}.md`
    link.click()
    URL.revokeObjectURL(link.href)
    pushLog('结果已下载为 Markdown')
  } catch (error) {
    errorMessage.value = error.message || '下载失败'
  }
}

async function fetchModes() {
  isFetchingModes.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/modes`)
    if (!response.ok) throw new Error('无法获取模式信息')
    const payload = await response.json()
    availableModes.value = payload.modes || {}
    defaultPrompt.value = payload.defaultPrompt || ''
    if (payload.maxImageMb) {
      uploadLimitMb.value = Number(payload.maxImageMb)
    }
    if (!prompt.value) {
      prompt.value = defaultPrompt.value
    }
    if (!(selectedMode.value in availableModes.value)) {
      const firstMode = Object.keys(availableModes.value)[0]
      if (firstMode) selectedMode.value = firstMode
    }
    serviceOnline.value = true
    loadError.value = ''
  } catch (error) {
    serviceOnline.value = false
    loadError.value = error.message
  } finally {
    isFetchingModes.value = false
  }
}

function setActivePage(index) {
  if (index < 0 || index >= pageResults.value.length) return
  if (activePageIndex.value === index) {
    applyLayoutFromPage(pageResults.value[index])
  } else {
    activePageIndex.value = index
  }
}

async function runInference() {
  if (!canRun.value) return
  isRunning.value = true
  errorMessage.value = ''
  inferenceResult.value = null
  pageResults.value = []
  activePageIndex.value = 0
  selectedHistoryId.value = ''
  isHistoryView.value = false
  progressInfo.value = { stage: 'pending', percent: 0, message: '准备开始...', current: 0, total: 100 }
  pushLog('开始推理任务')

  let taskId = null

  try {
    // 1. 创建任务 ID
    const taskRes = await fetch(`${API_BASE_URL}/api/task/create`, { method: 'POST' })
    if (taskRes.ok) {
      const taskData = await taskRes.json()
      taskId = taskData.taskId
    }

    // 2. 如果获取到 taskId，启动 SSE 监听进度
    if (taskId) {
      progressEventSource.value = new EventSource(`${API_BASE_URL}/api/progress/${taskId}`)
      
      progressEventSource.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          progressInfo.value = {
            stage: data.stage || '',
            percent: data.percent || 0,
            message: data.message || '',
            current: data.current || 0,
            total: data.total || 100,
          }
        } catch (e) {
          console.warn('解析进度数据失败:', e)
        }
      }

      progressEventSource.value.addEventListener('complete', () => {
        if (progressEventSource.value) {
          progressEventSource.value.close()
          progressEventSource.value = null
        }
      })

      progressEventSource.value.onerror = () => {
        if (progressEventSource.value) {
          progressEventSource.value.close()
          progressEventSource.value = null
        }
      }
    }

    // 3. 发起 OCR 请求
    const form = new FormData()
    form.append('mode', selectedMode.value)
    form.append('prompt', prompt.value || defaultPrompt.value)
    form.append('image', selectedFile.value)
    if (taskId) {
      form.append('task_id', taskId)
    }

    const response = await fetch(`${API_BASE_URL}/api/ocr`, {
      method: 'POST',
      body: form,
    })

    if (!response.ok) {
      let detail = '推理失败'
      try {
        const errBody = await response.json()
        detail = errBody.detail || errBody.message || detail
      } catch {
        detail = await response.text()
      }
      throw new Error(detail)
    }

    const payload = await response.json()
    applyResultPayload(payload, { fromHistory: false })
    progressInfo.value = { stage: 'complete', percent: 100, message: '识别完成！', current: 100, total: 100 }
    pushLog(`推理完成，耗时 ${payload.durationMs.toFixed(0)} ms`)
    fetchHistory()
  } catch (error) {
    errorMessage.value = error.message || '推理失败，请稍后重试'
    progressInfo.value = { stage: 'error', percent: 0, message: errorMessage.value, current: 0, total: 100 }
    pushLog(`推理失败：${errorMessage.value}`)
  } finally {
    isRunning.value = false
    // 关闭 SSE 连接
    if (progressEventSource.value) {
      progressEventSource.value.close()
      progressEventSource.value = null
    }
  }
}

function selectMode(key) {
  selectedMode.value = key
  pushLog(`切换模式：${availableModes.value[key]?.label || key}`)
}

function getStageLabel(stage) {
  const labels = {
    pending: '等待中',
    upload: '上传中',
    preprocessing: '预处理',
    inference: '推理中',
    postprocessing: '后处理',
    complete: '已完成',
    error: '出错',
  }
  return labels[stage] || stage
}

async function copyOutput() {
  if (!inferenceResult.value?.text) return
  await navigator.clipboard.writeText(inferenceResult.value.text)
  pushLog('推理结果已复制到剪贴板')
}

onMounted(() => {
  fetchModes()
  fetchHistory()
})

watch(activePageIndex, (newIndex) => {
  const targetPage = pageResults.value[newIndex]
  if (targetPage) {
    applyLayoutFromPage(targetPage)
  }
})

watch(pageResults, (pages) => {
  if (!pages.length) {
    resetLayoutState()
    return
  }
  if (activePageIndex.value >= pages.length) {
    activePageIndex.value = pages.length - 1
    return
  }
  applyLayoutFromPage(pages[activePageIndex.value])
})

watch(selectedRegionSnippet, () => {
  regionOutputView.value = 'raw'
})

onBeforeUnmount(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  // 清理 SSE 连接
  if (progressEventSource.value) {
    progressEventSource.value.close()
    progressEventSource.value = null
  }
})

const isSidebarCollapsed = ref(false)
const showSettings = ref(false)
</script>

<template>
  <div class="page layout-shell">
    <aside class="history-sidebar" :class="{ collapsed: isSidebarCollapsed }">
      <button class="collapse-btn" type="button" @click="isSidebarCollapsed = !isSidebarCollapsed">
        <span v-if="isSidebarCollapsed">▶</span>
        <span v-else>◀</span>
      </button>

      <div v-if="!isSidebarCollapsed" class="sidebar-content">
        <div class="sidebar-header">
          <div>
            <p class="eyebrow">历史记录</p>
            <h3>推理列表</h3>
          </div>
          <button class="ghost" type="button" @click="fetchHistory" :disabled="isLoadingHistory">
            {{ isLoadingHistory ? '刷新中...' : '刷新' }}
          </button>
        </div>

        <p v-if="historyError" class="error sidebar-error">{{ historyError }}</p>
        <div v-if="historyItems.length" class="sidebar-list">
          <button
            v-for="item in historyItems"
            :key="item.id"
            type="button"
            class="sidebar-item"
            :class="{ active: selectedHistoryId === item.id }"
            @click="loadHistory(item.id)"
            :disabled="isRunning"
          >
            <div class="item-title">
              <strong>{{ item.fileName || '未命名文件' }}</strong>
              <small>{{ item.createdAt || '--' }}</small>
            </div>
            <p class="muted">
              模式：{{ availableModes[item.mode]?.label || item.mode || '--' }} · 页：{{ item.pages || 1 }} · {{ item.isPdf ? 'PDF' : '图像' }}
            </p>
          </button>
        </div>
        <p v-else class="muted">暂无缓存历史</p>

        <button class="sidebar-settings" type="button" @click="showSettings = true">
          打开设置
        </button>
      </div>
    </aside>

    <main class="main-area">
      <HeroSection
        :service-online="serviceOnline"
        :is-history-view="isHistoryView"
        :api-base-url="API_BASE_URL"
        :load-error="loadError"
        :available-mode-count="Object.keys(availableModes).length"
        :last-duration="lastDuration"
        :last-run-at="lastRunAt"
      />

      <div class="workspace">
        <section class="panel workflow-panel">
          <UploadCard
            :has-image="hasImage"
            :is-pdf-upload="isPdfUpload"
            :selected-file="selectedFile"
            :upload-limit-label="uploadLimitLabel"
            :format-bytes="formatBytes"
            :preview-url="previewUrl"
            :on-file-change="handleFileChange"
            :on-drag-over="handleDragOver"
            :on-drop="handleDrop"
            :on-paste="handlePaste"
            :on-clear="clearImage"
          />

          <ActionCard
            :can-run="canRun"
            :is-running="isRunning"
            :run-inference="runInference"
            :error-message="errorMessage"
            :is-history-view="isHistoryView"
            :progress-info="progressInfo"
            :get-stage-label="getStageLabel"
          />

          <OutputCard
            :inference-result="inferenceResult"
            :is-running="isRunning"
            :download-markdown="downloadMarkdown"
            :copy-output="copyOutput"
          />

          <MetaCard
            :inference-result="inferenceResult"
            :available-modes="availableModes"
            :format-bytes="formatBytes"
          />

          <LogCard :activity-log="activityLog" />
        </section>

        <section class="panel visual-panel">
          <VisualPreviewCard
            :has-image="hasImage"
            :has-layout="hasLayout"
            :preview-mode="previewMode"
            :set-preview-mode="setPreviewMode"
            :page-results="pageResults"
            :active-page-index="activePageIndex"
            :set-active-page="setActivePage"
            :preview-image-src="previewImageSrc"
            :layout-regions="layoutRegions"
            :active-region-key="activeRegionKey"
            :handle-region-select="handleRegionSelect"
            :box-percent-style="boxPercentStyle"
            :aspect-ratio-style="aspectRatioStyle"
            :selected-file="selectedFile"
            :format-bytes="formatBytes"
            :available-modes="availableModes"
            :selected-mode="selectedMode"
            :is-pdf-upload="isPdfUpload"
          />

          <LayoutDetailsCard
            :has-layout="hasLayout"
            :layout-regions="layoutRegions"
            :active-region-key="activeRegionKey"
            :handle-region-select="handleRegionSelect"
            :selected-region="selectedRegion"
            :selected-region-snippet="selectedRegionSnippet"
            :copy-selected-region="copySelectedRegion"
            v-model:region-output-view="regionOutputView"
            :region-has-html-table="regionHasHtmlTable"
            :region-html-table-output="regionHtmlTableOutput"
            :region-markdown-table-output="regionMarkdownTableOutput"
          />

          <PageTextCard
            :current-page="currentPage"
            :current-page-clean-text="currentPageCleanText"
            :copy-current-page-text="copyCurrentPageText"
            :active-page-index="activePageIndex"
          />
        </section>
      </div>
    </main>

    <div v-if="showSettings" class="settings-modal">
      <div class="settings-overlay" @click="showSettings = false"></div>
      <section class="settings-panel">
        <header class="settings-header">
          <div>
            <p class="eyebrow">配置</p>
          </div>
        </header>
        <button class="settings-close" type="button" @click="showSettings = false">✕</button>

        <div class="settings-grid">
          <ModeCard
            :mode-cards="modeCards"
            :is-fetching-modes="isFetchingModes"
            :on-fetch-modes="fetchModes"
            :on-select-mode="selectMode"
          />

          <PromptCard v-model="prompt" />
        </div>
      </section>
    </div>
  </div>
</template>
