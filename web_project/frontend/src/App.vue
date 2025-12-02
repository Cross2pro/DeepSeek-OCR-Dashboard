<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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
</script>

<template>
  <div class="page">
    <header class="hero">
      <div>
        <p class="eyebrow">DeepSeek OCR 控制台</p>
        <h1>本地 DeepSeek-OCR 推理</h1>
        <p class="subtitle">
          上传图片、选择模式，即可通过 FastAPI 网关触发 DeepSeek-OCR，本地 GPU 一次加载，多次复用。
        </p>
        <div class="status-row">
          <span class="status-pill" :class="serviceOnline ? 'online' : 'offline'">
            {{ serviceOnline ? '推理服务运行中' : '推理服务离线' }}
          </span>
          <span class="status-pill light" v-if="isHistoryView">历史记录浏览</span>
          <span class="status-pill light">API {{ API_BASE_URL }}</span>
          <span class="status-pill light" v-if="loadError">{{ loadError }}</span>
        </div>
      </div>
      <ul class="hero-metrics">
        <li>
          <span>可选模式</span>
          <strong>{{ Object.keys(availableModes).length || '--' }}</strong>
        </li>
        <li>
          <span>最近推理耗时</span>
          <strong>{{ lastDuration }}</strong>
        </li>
        <li>
          <span>最近推理时间</span>
          <strong>{{ lastRunAt || '--' }}</strong>
        </li>
      </ul>
    </header>

    <div class="workspace">
      <section class="panel workflow-panel">
        <article class="card step-card">
          <h2>流程</h2>
          <div class="steps">
            <div v-for="step in workflowSteps" :key="step.key" class="step" :class="step.status">
              <div class="step-index">
                <span></span>
              </div>
              <div>
                <p>{{ step.label }}</p>
                <small>{{ step.description }}</small>
              </div>
            </div>
          </div>
        </article>

        <article
          class="card upload-card"
          @dragover="handleDragOver"
          @drop="handleDrop"
        >
          <div class="card-header">
            <div>
              <h2>步骤 1 · 上传图片</h2>
              <p>支持 PNG、JPG、JPEG，最大 {{ uploadLimitLabel }} MB。</p>
            </div>
            <button v-if="hasImage" class="ghost" type="button" @click="clearImage">
              清空
            </button>
          </div>
          <label class="dropzone">
            <input type="file" accept="image/*,.pdf" @change="handleFileChange" hidden />
            <div v-if="hasImage" class="dropzone-preview">
              <img v-if="!isPdfUpload" :src="previewUrl" alt="preview" />
              <div v-else class="pdf-chip">PDF</div>
              <div>
                <strong>{{ selectedFile?.name }}</strong>
                <small>{{ formatBytes(selectedFile?.size) }}</small>
                <p>{{ isPdfUpload ? 'PDF 文档将按页拆分识别。' : '拖拽替换图片或再次点击上传。' }}</p>
              </div>
            </div>
            <div v-else class="dropzone-empty">
              <p>拖拽图片 / PDF 到此或点击上传</p>
              <small>我们不会上传到云端，所有推理都在本机完成。</small>
            </div>
          </label>

          <div class="paste-area">
            <label for="clipboard-upload">或使用粘贴上传</label>
            <textarea
              id="clipboard-upload"
              rows="2"
              placeholder="在此按 Ctrl+V / Cmd+V 粘贴截图或文件，自动加入上传队列"
              @paste="handlePaste"
            ></textarea>
            <small>支持图片与 PDF，超出大小限制会被忽略。</small>
          </div>
        </article>

        <article class="card mode-card">
          <div class="card-header">
            <div>
              <h2>步骤 2 · 选择模式</h2>
              <p>根据速度与质量的平衡点选择推理配置。</p>
            </div>
            <button class="ghost" type="button" @click="fetchModes" :disabled="isFetchingModes">
              {{ isFetchingModes ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="mode-grid">
            <button
              v-for="mode in modeCards"
              :key="mode.key"
              type="button"
              class="mode-tile"
              :class="{ active: mode.isActive }"
              @click="selectMode(mode.key)"
            >
              <div class="mode-title">
                <h3>{{ mode.label }}</h3>
                <small>{{ mode.key }}</small>
              </div>
              <p>{{ mode.description }}</p>
              <ul>
                <li>质量：{{ mode.quality }}</li>
                <li>速度：{{ mode.speed }}</li>
                <li>尺寸：{{ mode.base_size }} / {{ mode.image_size }}</li>
              </ul>
            </button>
          </div>
        </article>

        <article class="card prompt-card">
          <h2>步骤 3 · 配置提示词</h2>
          <textarea
            rows="4"
            v-model="prompt"
            placeholder="请输入包含 <image> 的提示词"
          ></textarea>
          <small>提示词会拼接在模型输入中，默认会自动添加 &lt;image&gt;。</small>
        </article>

        <article class="card action-card">
          <div class="action-content">
            <button class="primary" type="button" :disabled="!canRun" @click="runInference">
              {{ isRunning ? '推理中 ...' : '开始推理' }}
            </button>
            <p class="hint">
              推理会占用 GPU，请确保已经按 requirements 安装依赖并加载模型。
            </p>
            <p v-if="isHistoryView" class="hint">当前处于历史查看模式，上传新文件以重新推理。</p>
            <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
          </div>

          <!-- 进度条区域 -->
          <div v-if="isRunning || progressInfo.stage === 'complete'" class="progress-section">
            <div class="progress-header">
              <span class="progress-stage" :class="progressInfo.stage">
                {{ getStageLabel(progressInfo.stage) }}
              </span>
              <span class="progress-percent">{{ progressInfo.percent }}%</span>
            </div>
            <div class="progress-bar-container">
              <div 
                class="progress-bar-fill" 
                :class="progressInfo.stage"
                :style="{ width: progressInfo.percent + '%' }"
              ></div>
            </div>
            <p class="progress-message">{{ progressInfo.message }}</p>
          </div>
        </article>

        <article class="card log-card">
          <h2>推理日志</h2>
          <ul v-if="activityLog.length">
            <li v-for="item in activityLog" :key="item.id">
              <strong>{{ item.timestamp }}</strong>
              <span>{{ item.message }}</span>
            </li>
          </ul>
          <p v-else class="muted">暂无日志</p>
        </article>

        <article class="card history-card">
          <div class="card-header">
            <div>
              <h2>历史记录</h2>
              <p>缓存最近的推理结果，包含图像和 PDF 预览。</p>
            </div>
            <button class="ghost" type="button" @click="fetchHistory" :disabled="isLoadingHistory">
              {{ isLoadingHistory ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <p v-if="historyError" class="error">{{ historyError }}</p>
          <ul v-if="historyItems.length" class="history-list">
            <li v-for="item in historyItems" :key="item.id" :class="{ active: selectedHistoryId === item.id }">
              <div>
                <strong>{{ item.fileName || '未命名文件' }}</strong>
                <small>{{ item.createdAt || '--' }}</small>
                <p class="muted">
                  模式：{{ availableModes[item.mode]?.label || item.mode || '--' }} · 页数：{{ item.pages || 1 }} · {{ item.isPdf ? 'PDF' : '图像' }}
                </p>
              </div>
              <button type="button" class="ghost" @click="loadHistory(item.id)" :disabled="isRunning">
                {{ selectedHistoryId === item.id ? '查看中' : '查看' }}
              </button>
            </li>
          </ul>
          <p v-else class="muted">暂无缓存历史</p>
        </article>

        <article class="card output-card">
          <div class="card-header">
            <div>
              <h2>推理输出</h2>
              <p>DeepSeek-OCR 将解析结构化文本。</p>
            </div>
            <div class="output-actions">
              <button type="button" class="ghost" :disabled="!inferenceResult?.text" @click="downloadMarkdown">
                下载
              </button>
              <button type="button" class="ghost" :disabled="!inferenceResult?.text" @click="copyOutput">
                复制
              </button>
            </div>
          </div>
          <div class="output-body" :class="{ loading: isRunning }">
            <p v-if="isRunning" class="muted">推理进行中，请稍候...</p>
            <p v-else-if="!inferenceResult" class="muted">等待推理结果...</p>
            <pre v-else>{{ inferenceResult.text }}</pre>
          </div>
        </article>

        <article class="card meta-card" v-if="inferenceResult">
          <h2>推理详情</h2>
          <ul>
            <li>
              <span>模式</span>
              <strong>{{ availableModes[inferenceResult.mode]?.label || inferenceResult.mode }}</strong>
            </li>
            <li>
              <span>耗时</span>
              <strong>{{ inferenceResult.durationMs.toFixed(0) }} ms</strong>
            </li>
            <li>
              <span>文件</span>
              <strong>{{ inferenceResult.fileName }} · {{ formatBytes(inferenceResult.fileSize) }}</strong>
            </li>
            <li>
              <span>提示词</span>
              <strong>{{ inferenceResult.prompt }}</strong>
            </li>
          </ul>
        </article>
      </section>

      <section class="panel visual-panel">
        <article class="card visual-card" v-if="hasImage">
          <div class="card-header">
            <div>
              <h2>可视化预览</h2>
              <p>查看原图、标注叠加或纯净重排视图。</p>
            </div>
            <div class="preview-mode-tabs" v-if="hasLayout">
              <button
                type="button"
                :class="{ active: previewMode === 'image' }"
                @click="setPreviewMode('image')"
              >
                原图
              </button>
              <button
                type="button"
                :class="{ active: previewMode === 'layout' }"
                @click="setPreviewMode('layout')"
              >
                标注
              </button>
              <button
                type="button"
                :class="{ active: previewMode === 'clean' }"
                @click="setPreviewMode('clean')"
              >
                纯净画布
              </button>
            </div>
          </div>
          <div class="page-tabs" v-if="pageResults.length">
            <button
              v-for="page in pageResults"
              :key="page.pageIndex"
              type="button"
              :class="{ active: activePageIndex === page.pageIndex }"
              @click="setActivePage(page.pageIndex)"
            >
              第 {{ page.pageIndex + 1 }} 页
            </button>
          </div>

          <div class="preview-stage" v-if="previewMode === 'image' || !hasLayout">
            <template v-if="previewImageSrc">
              <img :src="previewImageSrc" alt="preview" />
            </template>
            <p v-else class="muted helper">推理完成后将显示页面截图。</p>
          </div>

          <div class="preview-stage annotated" v-else-if="previewMode === 'layout'">
            <div class="annotated-view" :style="{ aspectRatio: aspectRatioStyle }">
              <img :src="previewImageSrc || previewUrl" alt="annotated" />
              <div class="overlay-layer">
                <button
                  v-for="region in layoutRegions"
                  :key="region.key"
                  class="overlay-box"
                  :class="{ active: region.key === activeRegionKey }"
                  :style="boxPercentStyle(region.box)"
                  type="button"
                  @click="handleRegionSelect(region.key)"
                >
                  <span>{{ region.label }}</span>
                </button>
              </div>
            </div>
          </div>

          <div class="preview-stage clean" v-else>
            <div class="clean-canvas" :style="{ aspectRatio: aspectRatioStyle }">
              <div
                v-for="region in layoutRegions"
                :key="`${region.key}-clean`"
                class="clean-fragment"
                :class="{ active: region.key === activeRegionKey }"
                :style="boxPercentStyle(region.box)"
                @click="handleRegionSelect(region.key)"
              >
                <small>{{ region.label }}</small>
                <p>{{ region.snippet || '...' }}</p>
              </div>
            </div>
            <p class="muted helper">隐藏原图，仅保留识别出的布局内容。</p>
          </div>

          <div class="preview-meta">
            <p><strong>{{ selectedFile?.name }}</strong></p>
            <p>{{ formatBytes(selectedFile?.size) }}</p>
            <p>模式：{{ availableModes[selectedMode]?.label || selectedMode }}</p>
            <p>文件类型：{{ isPdfUpload ? 'PDF 文档' : '图像' }}</p>
            <p v-if="pageResults.length">当前页：第 {{ activePageIndex + 1 }} 页</p>
          </div>
        </article>

        <article class="card visual-card empty" v-else>
          <p class="muted">上传后即可在此查看可视化结果。</p>
        </article>

        <article class="card layout-details-card" v-if="hasLayout">
          <div class="card-header">
            <div>
              <h2>标注详情</h2>
              <p>选择任意方框以查看位置信息与文本。</p>
            </div>
            <button class="ghost" type="button" :disabled="!selectedRegionSnippet" @click="copySelectedRegion">
              复制区域文本
            </button>
          </div>
          <div class="layout-chips">
            <button
              v-for="region in layoutRegions"
              :key="region.key"
              type="button"
              :class="{ active: region.key === activeRegionKey }"
              @click="handleRegionSelect(region.key)"
            >
              <span>{{ region.label }}</span>
              <small>#{{ region.box.index }}</small>
            </button>
          </div>
          <div v-if="selectedRegion" class="layout-inspector">
            <p><strong>类型：</strong>{{ selectedRegion.label }}</p>
            <p><strong>坐标：</strong>{{ selectedRegion.box.absolute.join(', ') }}</p>
            <div class="output-switch">
              <span>内容</span>
              <div class="output-tabs">
                <button
                  type="button"
                  :class="{ active: regionOutputView === 'raw' }"
                  @click="regionOutputView = 'raw'"
                >
                  原文
                </button>
                <button
                  type="button"
                  :class="{ active: regionOutputView === 'html' }"
                  :disabled="!regionHasHtmlTable"
                  @click="regionOutputView = 'html'"
                >
                  HTML 表格
                </button>
                <button
                  type="button"
                  :class="{ active: regionOutputView === 'markdown' }"
                  :disabled="!regionHasHtmlTable"
                  @click="regionOutputView = 'markdown'"
                >
                  Markdown 表格
                </button>
              </div>
            </div>
            <p v-if="selectedRegionSnippet && !regionHasHtmlTable" class="muted helper">
              未检测到表格标签，显示原文。
            </p>
            <div v-if="regionOutputView === 'html' && regionHtmlTableOutput" class="html-preview" v-html="regionHtmlTableOutput"></div>
            <pre v-else-if="regionOutputView === 'markdown' && regionMarkdownTableOutput">{{ regionMarkdownTableOutput }}</pre>
            <pre v-else>{{ selectedRegionSnippet || '该区域暂未匹配到文本，可参考全量输出。' }}</pre>
          </div>
          <p v-else class="muted">选择任意区域以查看具体内容。</p>
        </article>

        <article class="card layout-details-card muted-card" v-else>
          <p class="muted">完成一次推理后，可在此查看标注详情。</p>
        </article>

        <article class="card page-text-card" v-if="currentPage">
          <div class="card-header">
            <div>
              <h2>当前页文本</h2>
              <p>第 {{ currentPage.pageIndex + 1 }} 页识别结果</p>
            </div>
            <button class="ghost" type="button" :disabled="!currentPageCleanText" @click="copyCurrentPageText">
              复制当前页
            </button>
          </div>
          <pre>{{ currentPageCleanText || '暂无文本' }}</pre>
        </article>

      </section>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.hero {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.5rem 2rem;
  background: linear-gradient(135deg, #0f172a, #1e1b4b);
  color: #f8fafc;
  border-radius: 20px;
}

.eyebrow {
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-size: 0.75rem;
  opacity: 0.8;
  margin-bottom: 0.5rem;
}

.hero h1 {
  font-size: clamp(1.8rem, 4vw, 2.6rem);
  font-weight: 700;
  margin-bottom: 0.5rem;
}

.subtitle {
  max-width: 640px;
  opacity: 0.9;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.status-pill {
  padding: 0.35rem 0.9rem;
  border-radius: 999px;
  font-size: 0.85rem;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.status-pill.online {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.status-pill.offline {
  background: rgba(248, 113, 113, 0.2);
  color: #f87171;
}

.status-pill.light {
  background: rgba(148, 163, 184, 0.3);
  color: #e2e8f0;
}

.hero-metrics {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  list-style: none;
}

.hero-metrics li {
  background: rgba(15, 23, 42, 0.5);
  padding: 1rem 1.2rem;
  border-radius: 1rem;
  min-width: 160px;
}

.hero-metrics span {
  font-size: 0.85rem;
  opacity: 0.8;
}

.hero-metrics strong {
  display: block;
  margin-top: 0.35rem;
  font-size: 1.4rem;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(320px, 1.2fr) minmax(420px, 1.8fr);
  gap: 1.5rem;
  align-items: start;
}

.workflow-panel,
.visual-panel {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.visual-panel {
  position: sticky;
  top: 2rem;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.card {
  background: #ffffff;
  border-radius: 18px;
  padding: 1.5rem;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
  border: 1px solid rgba(15, 23, 42, 0.05);
}

.card h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
  color: #0f172a;
}

.card p {
  color: #334155;
}

.card small {
  color: #64748b;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.step {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.6rem 0.8rem;
  border-radius: 0.9rem;
  border: 1px dashed #e4e7ec;
}

.step .step-index span {
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 999px;
  background: #cbd5f5;
}

.step.done {
  border-color: rgba(34, 197, 94, 0.5);
}

.step.done .step-index span {
  background: #22c55e;
}

.step.active {
  border-color: rgba(59, 130, 246, 0.6);
}

.step.active .step-index span {
  background: #3b82f6;
}

.step small {
  color: #98a2b3;
}

.upload-card .dropzone {
  display: block;
  border: 2px dashed #cbd5f5;
  border-radius: 1.2rem;
  padding: 1.2rem;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.dropzone:hover {
  border-color: #6366f1;
}

.dropzone-empty {
  text-align: center;
  color: #94a3b8;
}

.dropzone-preview {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.dropzone-preview img {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: 0.8rem;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.pdf-chip {
  width: 96px;
  height: 96px;
  border-radius: 0.8rem;
  border: 2px dashed rgba(99, 102, 241, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: #4c1d95;
  background: rgba(99, 102, 241, 0.08);
}

.paste-area {
  margin-top: 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.paste-area textarea {
  width: 100%;
  border: 1px dashed rgba(99, 102, 241, 0.35);
  border-radius: 0.9rem;
  padding: 0.65rem 0.8rem;
  font-size: 0.95rem;
  resize: none;
  background: #f8fafc;
  color: #0f172a;
}

.paste-area label {
  font-weight: 600;
  color: #0f172a;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.mode-tile {
  text-align: left;
  border-radius: 1rem;
  border: 1px solid rgba(99, 102, 241, 0.2);
  padding: 1rem;
  cursor: pointer;
  background: #f8fafc;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.mode-tile.active {
  border-color: #6366f1;
  background: #eef2ff;
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.15);
}

.mode-tile h3 {
  margin: 0;
  font-size: 1.05rem;
}

.mode-tile ul {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  color: #475467;
  font-size: 0.9rem;
}

.mode-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.prompt-card textarea {
  width: 100%;
  border: 1px solid #e4e7ec;
  border-radius: 1rem;
  padding: 0.9rem;
  font-size: 0.95rem;
  min-height: 130px;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, SFMono, Menlo, Consolas, 'Liberation Mono', monospace;
}

.action-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.action-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

/* 进度条样式 */
.progress-section {
  width: 100%;
  padding: 1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 1rem;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.progress-stage {
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #e0e7ff;
  color: #4338ca;
}

.progress-stage.pending {
  background: #f1f5f9;
  color: #64748b;
}

.progress-stage.upload,
.progress-stage.preprocessing {
  background: #fef3c7;
  color: #d97706;
}

.progress-stage.inference {
  background: #dbeafe;
  color: #2563eb;
  animation: pulse 1.5s ease-in-out infinite;
}

.progress-stage.postprocessing {
  background: #d1fae5;
  color: #059669;
}

.progress-stage.complete {
  background: #d1fae5;
  color: #059669;
}

.progress-stage.error {
  background: #fee2e2;
  color: #dc2626;
}

.progress-percent {
  font-size: 1.1rem;
  font-weight: 700;
  color: #4338ca;
}

.progress-bar-container {
  width: 100%;
  height: 10px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
  transition: width 0.3s ease;
}

.progress-bar-fill.inference {
  background: linear-gradient(90deg, #3b82f6 0%, #6366f1 50%, #8b5cf6 100%);
  background-size: 200% 100%;
  animation: shimmer 2s linear infinite;
}

.progress-bar-fill.complete {
  background: linear-gradient(90deg, #10b981 0%, #22c55e 100%);
}

.progress-bar-fill.error {
  background: linear-gradient(90deg, #ef4444 0%, #f87171 100%);
}

.progress-message {
  font-size: 0.9rem;
  color: #64748b;
  margin: 0;
  text-align: center;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.primary {
  min-width: 180px;
  padding: 0.75rem 1.3rem;
  background: #6366f1;
  border: none;
  border-radius: 999px;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ghost {
  border: 1px solid rgba(99, 102, 241, 0.3);
  background: transparent;
  padding: 0.35rem 0.9rem;
  border-radius: 999px;
  cursor: pointer;
  color: #4c1d95;
}

.hint {
  color: #94a3b8;
  margin-top: 0.6rem;
}

.error {
  color: #ef4444;
  margin-top: 0.4rem;
}

.log-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.log-card li {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  color: #475467;
}

.log-card strong {
  font-size: 0.85rem;
  color: #1d4ed8;
}

.history-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.history-card li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  border: 1px dashed #e2e8f0;
  padding: 0.8rem;
  border-radius: 0.9rem;
}

.history-card li.active {
  border-color: #6366f1;
  background: #eef2ff;
}

.history-card strong {
  display: block;
  color: #0f172a;
}

.history-card small {
  color: #64748b;
}

.history-card .muted {
  margin: 0.2rem 0 0;
}

.muted {
  color: #94a3b8;
}

.preview-stage {
  border-radius: 1rem;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  background: #f8fafc;
  padding: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 420px;
}

.preview-stage img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 0.75rem;
}

.visual-card.empty {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-mode-tabs {
  display: flex;
  gap: 0.4rem;
}

.preview-mode-tabs button {
  padding: 0.3rem 0.85rem;
  border-radius: 999px;
  border: 1px solid rgba(99, 102, 241, 0.25);
  background: transparent;
  color: #4c1d95;
  font-size: 0.85rem;
  cursor: pointer;
}

.preview-mode-tabs button.active {
  background: #6366f1;
  color: #fff;
  border-color: #6366f1;
}

.page-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.8rem;
}

.page-tabs button {
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.6);
  background: transparent;
  padding: 0.35rem 0.8rem;
  font-size: 0.85rem;
  cursor: pointer;
  color: #475467;
}

.page-tabs button.active {
  border-color: #6366f1;
  background: #eef2ff;
  color: #4c1d95;
}

.annotated-view,
.clean-canvas {
  position: relative;
  width: 100%;
  aspect-ratio: v-bind(aspectRatioStyle);
  border-radius: 0.75rem;
  overflow: hidden;
}

.annotated-view img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.overlay-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.overlay-box {
  position: absolute;
  border: 2px solid rgba(99, 102, 241, 0.9);
  background: rgba(99, 102, 241, 0.18);
  border-radius: 0.6rem;
  color: #1f2937;
  font-size: 0.75rem;
  padding: 0.15rem 0.45rem;
  pointer-events: auto;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease;
  display: flex;
  align-items: flex-start;
}

.overlay-box span {
  background: rgba(15, 23, 42, 0.75);
  color: #fff;
  padding: 0.05rem 0.2rem;
  border-radius: 0.4rem;
}

.overlay-box.active {
  border-color: #f97316;
  background: rgba(249, 115, 22, 0.2);
  transform: translateY(-1px);
}

.clean-canvas {
  background: linear-gradient(135deg, #fafafa, #f1f5f9);
  border: 1px dashed rgba(99, 102, 241, 0.25);
  padding: 0;
}

.clean-fragment {
  position: absolute;
  border-radius: 0.8rem;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(15, 23, 42, 0.1);
  padding: 0.35rem;
  font-size: 0.75rem;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.clean-fragment small {
  font-weight: 600;
  color: #475569;
}

.clean-fragment.active {
  border-color: #f97316;
  box-shadow: 0 8px 20px rgba(249, 115, 22, 0.2);
}

.preview-meta {
  margin-top: 1rem;
  background: #f8fafc;
  padding: 0.75rem;
  border-radius: 1rem;
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.preview-meta p {
  margin: 0.1rem 0;
  color: #475467;
}

.helper {
  margin-top: 0.5rem;
  font-size: 0.85rem;
}

.layout-details-card {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.layout-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.layout-chips button {
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.6);
  background: transparent;
  padding: 0.35rem 0.7rem;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  cursor: pointer;
  color: #475467;
}

.layout-chips button.active {
  border-color: #f97316;
  color: #f97316;
  background: rgba(249, 115, 22, 0.12);
}

.muted-card {
  border-style: dashed;
  text-align: center;
  color: #94a3b8;
}

.page-text-card pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 0.8rem;
  border-radius: 0.9rem;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
}

.layout-inspector pre {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 0.75rem;
  padding: 0.7rem;
  white-space: pre-wrap;
  max-height: 220px;
  overflow: auto;
  margin-top: 0.4rem;
}

.output-actions {
  display: flex;
  gap: 0.5rem;
}

.output-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.25rem 0 0.5rem;
}

.output-switch span {
  font-weight: 600;
  color: #0f172a;
}

.output-tabs {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.output-tabs button {
  border-radius: 999px;
  border: 1px solid rgba(99, 102, 241, 0.3);
  background: transparent;
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;
  color: #4c1d95;
}

.output-tabs button.active {
  background: #6366f1;
  color: #fff;
  border-color: #6366f1;
}

.output-tabs button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.output-card pre {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  background: #0f172a;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: 1rem;
  max-height: 360px;
  overflow: auto;
}

.output-body {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.output-body.loading {
  color: #0f172a;
}

.html-preview {
  width: 100%;
  text-align: left;
}

.html-preview table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 0.75rem;
}

.html-preview th,
.html-preview td {
  border: 1px solid #e2e8f0;
  padding: 0.5rem;
  text-align: left;
  font-size: 0.9rem;
  color: #0f172a;
}

.html-preview th {
  background: #f8fafc;
  font-weight: 600;
}

.meta-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.meta-card li {
  display: flex;
  justify-content: space-between;
  color: #475467;
  border-bottom: 1px solid rgba(226, 232, 240, 0.7);
  padding-bottom: 0.4rem;
}

.meta-card strong {
  color: #0f172a;
}

@media (max-width: 1024px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .visual-panel {
    position: static;
  }

  .hero-metrics {
    width: 100%;
    justify-content: space-between;
  }
}

@media (max-width: 640px) {
  .card {
    padding: 1.2rem;
  }

  .mode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
