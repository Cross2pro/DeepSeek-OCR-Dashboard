<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

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

const modeCards = computed(() =>
  Object.entries(availableModes.value).map(([key, meta]) => ({
    key,
    ...meta,
    isActive: key === selectedMode.value,
  }))
)

const hasImage = computed(() => Boolean(selectedFile.value))
const canRun = computed(() => hasImage.value && Boolean(selectedMode.value) && !isRunning.value)
const uploadLimitLabel = computed(() =>
  uploadLimitMb.value ? uploadLimitMb.value.toFixed(1) : '15'
)

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

function attachFile(file) {
  if (!file) return
  selectedFile.value = file
  inferenceResult.value = null
  lastRunAt.value = ''
  errorMessage.value = ''

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = URL.createObjectURL(file)
  pushLog(`图片已就绪：${file.name}`)
}

function clearImage() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  selectedFile.value = null
  previewUrl.value = ''
  inferenceResult.value = null
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

async function runInference() {
  if (!canRun.value) return
  isRunning.value = true
  errorMessage.value = ''
  inferenceResult.value = null
  pushLog('开始推理任务')
  const form = new FormData()
  form.append('mode', selectedMode.value)
  form.append('prompt', prompt.value || defaultPrompt.value)
  form.append('image', selectedFile.value)

  try {
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
    inferenceResult.value = payload
    lastRunAt.value = new Date().toLocaleString()
    pushLog(`推理完成，耗时 ${payload.durationMs.toFixed(0)} ms`)
  } catch (error) {
    errorMessage.value = error.message || '推理失败，请稍后重试'
    pushLog(`推理失败：${errorMessage.value}`)
  } finally {
    isRunning.value = false
  }
}

function selectMode(key) {
  selectedMode.value = key
  pushLog(`切换模式：${availableModes.value[key]?.label || key}`)
}

async function copyOutput() {
  if (!inferenceResult.value?.text) return
  await navigator.clipboard.writeText(inferenceResult.value.text)
  pushLog('推理结果已复制到剪贴板')
}

onMounted(() => {
  fetchModes()
})

onBeforeUnmount(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
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

    <div class="grid">
      <section class="panel">
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
            <input type="file" accept="image/*" @change="handleFileChange" hidden />
            <div v-if="hasImage" class="dropzone-preview">
              <img :src="previewUrl" alt="preview" />
              <div>
                <strong>{{ selectedFile?.name }}</strong>
                <small>{{ formatBytes(selectedFile?.size) }}</small>
                <p>拖拽替换图片或再次点击上传。</p>
              </div>
            </div>
            <div v-else class="dropzone-empty">
              <p>拖拽图片到此或点击上传</p>
              <small>我们不会上传到云端，所有推理都在本机完成。</small>
            </div>
          </label>
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
          <div>
            <button class="primary" type="button" :disabled="!canRun" @click="runInference">
              {{ isRunning ? '推理中 ...' : '开始推理' }}
            </button>
            <p class="hint">
              推理会占用 GPU，请确保已经按 requirements 安装依赖并加载模型。
            </p>
            <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
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
      </section>

      <section class="panel result-panel">
        <article class="card preview-card" v-if="hasImage">
          <div class="preview">
            <img :src="previewUrl" alt="preview" />
          </div>
          <div class="preview-meta">
            <p><strong>{{ selectedFile?.name }}</strong></p>
            <p>{{ formatBytes(selectedFile?.size) }}</p>
            <p>模式：{{ availableModes[selectedMode]?.label || selectedMode }}</p>
          </div>
        </article>

        <article class="card preview-card" v-else>
          <p class="muted">上传后可在此预览图片。</p>
        </article>

        <article class="card output-card">
          <div class="card-header">
            <div>
              <h2>推理输出</h2>
              <p>DeepSeek-OCR 将解析结构化文本。</p>
            </div>
            <button type="button" class="ghost" :disabled="!inferenceResult?.text" @click="copyOutput">
              复制
            </button>
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

.grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1.5rem;
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
  align-items: center;
  justify-content: space-between;
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

.muted {
  color: #94a3b8;
}

.result-panel .preview {
  border-radius: 1rem;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.preview img {
  width: 100%;
  height: auto;
  display: block;
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
  .grid {
    grid-template-columns: 1fr;
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
