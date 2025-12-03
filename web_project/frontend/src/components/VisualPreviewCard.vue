<script setup>
defineProps({
  hasImage: {
    type: Boolean,
    default: false,
  },
  hasLayout: {
    type: Boolean,
    default: false,
  },
  previewMode: {
    type: String,
    default: 'image',
  },
  setPreviewMode: Function,
  pageResults: {
    type: Array,
    default: () => [],
  },
  activePageIndex: {
    type: Number,
    default: 0,
  },
  setActivePage: Function,
  previewImageSrc: {
    type: String,
    default: '',
  },
  layoutRegions: {
    type: Array,
    default: () => [],
  },
  activeRegionKey: {
    type: String,
    default: '',
  },
  handleRegionSelect: Function,
  boxPercentStyle: {
    type: Function,
    default: () => ({}),
  },
  aspectRatioStyle: {
    type: String,
    default: '4 / 3',
  },
  selectedFile: {
    type: Object,
    default: null,
  },
  formatBytes: {
    type: Function,
    default: () => '',
  },
  availableModes: {
    type: Object,
    default: () => ({}),
  },
  selectedMode: {
    type: String,
    default: '',
  },
  isPdfUpload: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
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
        <img :src="previewImageSrc" alt="annotated" />
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
</template>
