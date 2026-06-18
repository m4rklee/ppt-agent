<template>
  <div class="upload-page">
    <div class="upload-card">
      <div class="card-header">
        <h2>开始生成</h2>
        <p class="subtitle">上传 PDF 与参考 PPT，自动生成演示文稿</p>
      </div>

      <div class="form-group">
        <label for="pdf-upload" class="field-label">
          PDF 文档
          <span class="required">必填</span>
        </label>
        <label for="pdf-upload" class="btn-outline file-trigger">
          {{ pdfFile ? pdfFile.name : '选择 PDF 文件' }}
        </label>
        <input
          id="pdf-upload"
          type="file"
          accept=".pdf"
          class="file-input"
          @change="handleFileUpload($event, 'pdf')"
        />
        <p v-if="pdfFile" class="file-hint">已选择</p>
      </div>

      <div class="form-group">
        <label for="pptx-upload" class="field-label">
          参考 PPT
          <span class="optional">默认内置模板</span>
        </label>
        <label for="pptx-upload" class="btn-outline file-trigger">
          {{ pptxFile ? pptxFile.name : '选择本地 PPTX 文件' }}
        </label>
        <input
          id="pptx-upload"
          type="file"
          accept=".pptx"
          class="file-input"
          @change="handleFileUpload($event, 'pptx')"
        />
        <div class="preview-actions">
          <button
            type="button"
            class="btn-outline preview-btn"
            :disabled="previewState.loading || !canPreview"
            @click="previewPptx"
          >
            预览
          </button>
          <p v-if="pptxFile" class="default-fallback-tip">
            当前使用：本地 PPT（{{ pptxFile.name }}）
          </p>
          <p v-else-if="defaultTemplateAvailable" class="default-fallback-tip">
            当前使用：内置模板（{{ defaultTemplateName || 'source.pptx' }}）
          </p>
          <p v-else-if="!pptxFile" class="default-fallback-tip">暂无默认模板，请上传参考PPT后预览</p>
        </div>
      </div>

      <div class="form-group">
        <div class="field-label">目标页数</div>
        <div class="mode-toggle" role="radiogroup" aria-label="目标页数">
          <button
            type="button"
            :class="['mode-option', { active: pageMode === 'fixed' }]"
            @click="pageMode = 'fixed'"
          >
            指定
            <span>手动输入页数</span>
          </button>
          <button
            type="button"
            :class="['mode-option', { active: pageMode === 'auto' }]"
            @click="pageMode = 'auto'"
          >
            自动
            <span>AI 根据文档决定</span>
          </button>
        </div>
        <input
          v-if="pageMode === 'fixed'"
          id="pages-input"
          v-model.number="selectedPages"
          type="number"
          min="1"
          max="100"
          step="1"
          class="select-input pages-input"
          placeholder="请输入页数，如 12"
        />
        <p v-else class="file-hint">页数由 AI 根据文档结构与内容密度自动生成</p>
      </div>

      <div class="form-group">
        <div class="field-label">生成模式</div>
        <div class="mode-toggle" role="radiogroup" aria-label="生成模式">
          <button
            type="button"
            :class="['mode-option', { active: generationMode === 'auto' }]"
            @click="generationMode = 'auto'"
          >
            Auto
            <span>全自动生成</span>
          </button>
          <button
            type="button"
            :class="['mode-option', { active: generationMode === 'ask' }]"
            @click="generationMode = 'ask'"
          >
            Ask
            <span>大纲确认后继续</span>
          </button>
        </div>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      <div class="preview-panel">
        <p class="preview-status">
          <template v-if="previewState.loading">正在生成预览…</template>
          <template v-else-if="previewState.error">{{ previewState.error }}</template>
          <template v-else-if="previewState.images.length">
            已预览 {{ previewState.images.length }} 页（{{ previewState.sourceLabel }}）
          </template>
          <template v-else>未预览</template>
        </p>
        <div v-if="previewState.images.length" class="preview-grid">
          <img
            v-for="(img, idx) in previewState.images"
            :key="img.name"
            :src="img.url"
            :alt="img.name"
            class="preview-thumb"
            @click="openLightbox(idx)"
          />
        </div>
      </div>

      <button
        class="btn-primary submit-btn"
        :disabled="!pdfFile || !canUseReferencePpt || submitting"
        @click="goToGenerate"
      >
        {{ submitting ? '上传中…' : '开始生成' }}
      </button>
    </div>

    <div v-if="lightboxOpen && currentLightboxImage" class="lightbox-overlay" @click.self="closeLightbox">
      <button type="button" class="lightbox-close" @click="closeLightbox">关闭</button>
      <button type="button" class="lightbox-nav left" @click="showPrev">‹</button>
      <img
        :src="currentLightboxImage.url"
        :alt="currentLightboxImage.name"
        class="lightbox-image"
      />
      <button type="button" class="lightbox-nav right" @click="showNext">›</button>
      <p class="lightbox-counter">{{ lightboxIndex + 1 }} / {{ previewState.images.length }}</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'UploadComponent',
  data() {
    return {
      pptxFile: null,
      pdfFile: null,
      selectedPages: 6,
      pageMode: 'fixed',
      generationMode: 'auto',
      errorMessage: '',
      submitting: false,
      defaultTemplateAvailable: null,
      defaultTemplateName: '',
      previewState: {
        loading: false,
        error: '',
        images: [],
        sourceLabel: '',
      },
      lightboxOpen: false,
      lightboxIndex: 0,
    }
  },
  async created() {
    await this.probeDefaultTemplate()
  },
  mounted() {
    window.addEventListener('keydown', this.handleLightboxKeydown)
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.handleLightboxKeydown)
  },
  computed: {
    currentLightboxImage() {
      if (!this.previewState.images.length) return null
      return this.previewState.images[this.lightboxIndex] || null
    },
    canPreview() {
      return this.canUseReferencePpt
    },
    canUseReferencePpt() {
      return this.defaultTemplateAvailable === true || !!this.pptxFile
    },
  },
  methods: {
    handleFileUpload(event, fileType) {
      const file = event.target.files[0]
      if (!file) return
      if (fileType === 'pptx') {
        this.pptxFile = file
        this.previewState.images = []
        this.previewState.error = ''
      } else if (fileType === 'pdf') {
        this.pdfFile = file
      }
      this.errorMessage = ''
    },
    async probeDefaultTemplate() {
      try {
        const res = await this.$axios.get('/api/ppt-preview/default-availability')
        this.defaultTemplateAvailable = !!res.data?.available
        this.defaultTemplateName = res.data?.template_name || ''
      } catch (error) {
        this.defaultTemplateAvailable = false
        this.defaultTemplateName = ''
      }
    },
    async requestPreview(formData, sourceLabel, isDefault = false) {
      this.previewState.loading = true
      this.previewState.error = ''
      try {
        const previewResp = await this.$axios.post('/api/ppt-preview', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        const previewId = previewResp.data.preview_id
        const imagesResp = await this.$axios.get(`/api/ppt-preview/${previewId}/images`)
        this.previewState.images = imagesResp.data.images || []
        this.previewState.sourceLabel = sourceLabel
      } catch (error) {
        console.error('Preview error:', error)
        this.previewState.images = []
        const status = error?.response?.status
        if (isDefault && status === 404) {
          this.defaultTemplateAvailable = false
          this.defaultTemplateName = ''
          this.previewState.error = '暂无默认模板，请上传参考PPT后预览'
        } else {
          this.previewState.error =
            error?.response?.data?.detail || '预览生成失败，请检查PPT格式'
        }
      } finally {
        this.previewState.loading = false
      }
    },
    async previewPptx() {
      if (this.pptxFile) {
        const formData = new FormData()
        formData.append('pptxFile', this.pptxFile)
        await this.requestPreview(formData, '已选参考PPT')
        return
      }
      if (this.defaultTemplateAvailable) {
        const formData = new FormData()
        formData.append('use_default', 'true')
        await this.requestPreview(
          formData,
          this.defaultTemplateName ? `默认模板（${this.defaultTemplateName}）` : '默认模板',
          true
        )
      }
    },
    openLightbox(index) {
      if (!this.previewState.images.length) return
      this.lightboxIndex = index
      this.lightboxOpen = true
    },
    closeLightbox() {
      this.lightboxOpen = false
    },
    showPrev() {
      const total = this.previewState.images.length
      if (!total) return
      this.lightboxIndex = (this.lightboxIndex - 1 + total) % total
    },
    showNext() {
      const total = this.previewState.images.length
      if (!total) return
      this.lightboxIndex = (this.lightboxIndex + 1) % total
    },
    handleLightboxKeydown(event) {
      if (!this.lightboxOpen) return
      if (event.key === 'Escape') {
        this.closeLightbox()
      } else if (event.key === 'ArrowLeft') {
        this.showPrev()
      } else if (event.key === 'ArrowRight') {
        this.showNext()
      }
    },
    async goToGenerate() {
      this.errorMessage = ''
      if (!this.canUseReferencePpt) {
        this.errorMessage = '暂无默认模板，请先上传参考 PPT 文件'
        return
      }
      if (!this.pdfFile) {
        this.errorMessage = '请先上传 PDF 文件'
        return
      }
      if (this.pageMode === 'fixed') {
        if (!Number.isInteger(this.selectedPages) || this.selectedPages < 1 || this.selectedPages > 100) {
          this.errorMessage = '目标页数请输入 1-100 的整数'
          return
        }
      }

      this.submitting = true
      try {
        await this.$axios.get('/')
      } catch (error) {
        console.error(error)
        this.errorMessage = '服务暂不可用，请稍后再试'
        this.submitting = false
        return
      }

      const formData = new FormData()
      if (this.pptxFile) {
        formData.append('pptxFile', this.pptxFile)
      } else {
        formData.append('useDefaultPptx', 'true')
      }
      formData.append('pdfFile', this.pdfFile)
      formData.append('pageMode', this.pageMode)
      if (this.pageMode === 'fixed') {
        formData.append('numberOfPages', this.selectedPages)
      }
      formData.append('generationMode', this.generationMode)

      try {
        const uploadResponse = await this.$axios.post('/api/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        const taskId = uploadResponse.data.task_id
        this.$router.push({ name: 'Generate', state: { taskId } })
      } catch (error) {
        console.error('Upload error:', error)
        this.errorMessage = '上传失败，请重试'
        this.submitting = false
      }
    },
  },
}
</script>

<style scoped>
.upload-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 48px);
  padding: 32px 20px;
}

.upload-card {
  width: 100%;
  max-width: 420px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 28px 24px;
  box-shadow: var(--shadow-md);
}

.card-header {
  margin-bottom: 24px;
}

.card-header h2 {
  margin: 0 0 6px;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text);
}

.subtitle {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.form-group {
  margin-bottom: 16px;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 6px;
}

.required {
  font-size: 0.75rem;
  color: var(--color-error);
  font-weight: 400;
}

.optional {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-weight: 400;
}

.file-input {
  display: none;
}

.file-trigger {
  cursor: pointer;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-hint {
  margin: 4px 0 0;
  font-size: 0.75rem;
  color: var(--color-success);
}

.preview-actions {
  margin-top: 8px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.preview-btn {
  font-size: 0.85rem;
  padding: 8px 10px;
}

.default-fallback-tip {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.select-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  color: var(--color-text);
  background: var(--color-surface);
  appearance: none;
}

.select-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.pages-input {
  margin-top: 10px;
}

.mode-toggle {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.mode-option {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: var(--radius-sm);
  padding: 10px;
  text-align: left;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
}

.mode-option span {
  display: block;
  margin-top: 4px;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  font-weight: 400;
}

.mode-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.error-message {
  margin: 0 0 12px;
  font-size: 0.85rem;
  color: var(--color-error);
}

.preview-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  padding: 10px;
  margin-bottom: 12px;
}

.preview-status {
  margin: 0;
  font-size: 0.82rem;
  color: var(--color-text-secondary);
}

.preview-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  max-height: 220px;
  overflow-y: auto;
}

.preview-thumb {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  display: block;
  cursor: zoom-in;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
  padding: 12px;
  font-size: 1rem;
}

.lightbox-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.78);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.lightbox-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 6px;
}

.lightbox-close {
  position: absolute;
  top: 16px;
  right: 16px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.6);
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  font-size: 1.4rem;
  line-height: 1;
  cursor: pointer;
}

.lightbox-nav.left {
  left: 16px;
}

.lightbox-nav.right {
  right: 16px;
}

.lightbox-counter {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 0.85rem;
  margin: 0;
}

@media (max-width: 768px) {
  .lightbox-nav {
    width: 38px;
    height: 38px;
  }
}
</style>
