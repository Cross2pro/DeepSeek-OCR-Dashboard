<script setup>
defineProps({
  hasImage: Boolean,
  isPdfUpload: Boolean,
  selectedFile: Object,
  uploadLimitLabel: {
    type: String,
    default: '',
  },
  formatBytes: {
    type: Function,
    default: () => '',
  },
  previewUrl: {
    type: String,
    default: '',
  },
  onFileChange: Function,
  onDragOver: Function,
  onDrop: Function,
  onPaste: Function,
  onClear: Function,
})
</script>

<template>
  <article
    class="card upload-card"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <div class="card-header">
      <div>
        <h2>步骤 1 · 上传图片</h2>
        <p>支持 PNG、JPG、JPEG，最大 {{ uploadLimitLabel }} MB。</p>
      </div>
      <button v-if="hasImage" class="ghost" type="button" @click="onClear">
        清空
      </button>
    </div>
    <label class="dropzone">
      <input type="file" accept="image/*,.pdf" @change="onFileChange" hidden />
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
        @paste="onPaste"
      ></textarea>
      <small>支持图片与 PDF，超出大小限制会被忽略。</small>
    </div>
  </article>
</template>
