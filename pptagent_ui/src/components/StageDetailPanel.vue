<template>
  <div class="stage-detail-panel">
    <div v-if="!stage" class="empty-state">
      <p>选择左侧步骤查看进度</p>
    </div>
    <template v-else>
      <h3 class="stage-heading">{{ stage.label }}</h3>

      <div v-if="loading" class="detail-section">
        <p class="muted">加载中…</p>
      </div>

      <div v-if="stage.status === 'running' && stageMessage" class="detail-section">
        <p class="running-hint">{{ stageMessage }}</p>
      </div>

      <div v-if="stage.status === 'failed' && stage.summary?.error" class="detail-section">
        <p class="error-text">{{ stage.summary.error }}</p>
      </div>

      <div v-if="error" class="detail-section">
        <p class="error-text">{{ error }}</p>
      </div>

      <!-- 主内容预览 -->
      <div v-if="stage.id === 'ppt_parse' && artifactData.image_stats" class="preview">
        <h4 class="preview-title">参考幻灯片</h4>
        <div class="image-grid" v-if="artifactData.slide_images">
          <img
            v-for="img in artifactData.slide_images.images"
            :key="img.name"
            :src="img.url"
            :alt="img.name"
            class="thumb"
          />
        </div>
      </div>

      <div v-if="stage.id === 'pdf_parse' && artifactData.pdf_images" class="preview">
        <h4 class="preview-title">提取的图片</h4>
        <div class="image-grid">
          <img
            v-for="img in artifactData.pdf_images.images"
            :key="img.name"
            :src="img.url"
            :alt="img.name"
            class="thumb"
          />
        </div>
      </div>

      <div v-if="stage.id === 'doc_refine' && artifactData.refined_doc" class="preview">
        <h4 class="preview-title">文档结构</h4>
        <ul class="section-tree">
          <li v-for="sec in artifactData.refined_doc.sections" :key="sec.title">
            <strong>{{ sec.title }}</strong>
            <ul v-if="sec.subsections">
              <li v-for="sub in sec.subsections" :key="sub.title">
                {{ sub.title }}
                <span class="muted" v-if="sub.summary"> — {{ truncate(sub.summary, 60) }}</span>
              </li>
            </ul>
          </li>
        </ul>
      </div>

      <div v-if="stage.id === 'template_prep' && artifactData.template_images" class="preview">
        <h4 class="preview-title">版式模板</h4>
        <div class="image-grid">
          <img
            v-for="img in artifactData.template_images.images"
            :key="img.name"
            :src="img.url"
            :alt="img.name"
            class="thumb"
          />
        </div>
      </div>

      <div v-if="stage.id === 'slide_induction' && artifactData.slide_induction" class="preview">
        <h4 class="preview-title">版式类型</h4>
        <ul class="layout-list">
          <li v-for="(cluster, name) in layoutEntries(artifactData.slide_induction)" :key="name">
            {{ name }}
            <span class="muted">（{{ (cluster.slides || []).length }} 页）</span>
          </li>
        </ul>
      </div>

      <div v-if="stage.id === 'outline' && artifactData.outline" class="preview">
        <h4 class="preview-title">演示大纲</h4>
        <ol class="outline-list">
          <li v-for="item in artifactData.outline" :key="item.slide">
            {{ item.purpose }}
          </li>
        </ol>
      </div>

      <div v-if="isAwaitingOutlineReview" class="preview outline-review">
        <h4 class="preview-title">确认演示大纲</h4>
        <p class="muted">可调整每页主题和所属章节，确认后将继续逐页生成。</p>
        <p v-if="reviewLoading" class="muted">正在加载待确认大纲…</p>
        <div v-else class="outline-editor">
          <div v-for="item in reviewOutline" :key="item.slide" class="outline-edit-row">
            <div class="outline-edit-index">第 {{ item.slide }} 页</div>
            <label>
              页面主题
              <input v-model.trim="item.purpose" type="text" class="outline-input" />
            </label>
            <label>
              所属章节
              <input v-model.trim="item.section" type="text" class="outline-input" />
            </label>
          </div>
          <p v-if="reviewError" class="error-text">{{ reviewError }}</p>
          <p v-if="reviewMessage" class="success-text">{{ reviewMessage }}</p>
          <button
            type="button"
            class="btn-primary review-submit"
            :disabled="reviewSubmitting || !isReviewValid"
            @click="submitOutlineReview"
          >
            {{ reviewSubmitting ? '提交中…' : '确认并继续生成' }}
          </button>
        </div>
      </div>

      <SlideGenProgress
        v-if="stage.id === 'slide_gen' && (stage.status === 'running' || stage.status === 'completed' || slideGen.total > 0)"
        :slides="slideGen.slides"
        :completed="slideGen.completed"
        :total="slideGen.total"
        :current-purpose="slideGen.current_purpose"
      />

      <div v-if="stage.id === 'done' && stage.status === 'completed' && downloadLink" class="preview">
        <div class="done-actions">
          <a :href="downloadLink" :download="filename" class="btn-primary done-download">
            下载 PPTX
          </a>
          <button
            type="button"
            class="btn-outline done-preview-btn"
            :disabled="finalPreview.loading"
            @click="previewFinalPpt"
          >
            {{ finalPreview.loading ? '预览生成中…' : '预览 PPTX' }}
          </button>
        </div>
        <p v-if="finalPreview.error" class="error-text final-preview-message">
          {{ finalPreview.error }}
        </p>
        <div v-if="finalPreview.images.length" class="final-preview-grid">
          <img
            v-for="(img, idx) in finalPreview.images"
            :key="img.name"
            :src="img.url"
            :alt="img.name"
            class="final-preview-thumb"
            @click="openFinalPreviewLightbox(idx)"
          />
        </div>
      </div>

      <!-- 技术详情（默认折叠） -->
      <details v-if="hasTechDetails" class="fold-section">
        <summary>技术详情</summary>
        <div class="fold-body">
          <div v-if="stage.inputs?.length" class="detail-section">
            <h4>输入</h4>
            <ul>
              <li v-for="item in stage.inputs" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div v-if="stage.outputs?.length" class="detail-section">
            <h4>输出</h4>
            <ul>
              <li v-for="item in stage.outputs" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div v-if="stageAgents.length" class="detail-section">
            <h4>参与 Agent</h4>
            <div class="agent-tags">
              <span v-for="name in stageAgents" :key="name" class="agent-tag">{{ name }}</span>
            </div>
          </div>
          <div v-if="stage.summary" class="detail-section">
            <h4>摘要</h4>
            <pre class="summary-json">{{ formatSummary(stage.summary) }}</pre>
          </div>
          <div v-if="stage.id === 'pdf_parse' && artifactData.source_md" class="detail-section">
            <h4>Markdown 原文</h4>
            <pre class="md-preview">{{ artifactData.source_md }}</pre>
          </div>
        </div>
      </details>

      <details v-if="hasAgentTraces && (stage.status === 'completed' || showAgentTraces)" class="fold-section">
        <summary>查看 Agent 调用记录（调试）</summary>
        <div class="fold-body">
          <AgentTracePanel
            :task-id="taskId"
            :stage-id="stage.id"
            :agent-names="stageAgents"
            :live-trace="liveAgentTrace"
            :live-slide-traces="liveSlideTraces"
            :embedded="true"
          />
        </div>
      </details>
    </template>

    <div
      v-if="finalLightboxOpen && currentFinalPreviewImage"
      class="final-lightbox-overlay"
      @click.self="closeFinalPreviewLightbox"
    >
      <button type="button" class="final-lightbox-close" @click="closeFinalPreviewLightbox">
        关闭
      </button>
      <button type="button" class="final-lightbox-nav left" @click="showFinalPreviewPrev">‹</button>
      <img
        :src="currentFinalPreviewImage.url"
        :alt="currentFinalPreviewImage.name"
        class="final-lightbox-image"
      />
      <button type="button" class="final-lightbox-nav right" @click="showFinalPreviewNext">›</button>
      <p class="final-lightbox-counter">
        {{ finalLightboxIndex + 1 }} / {{ finalPreview.images.length }}
      </p>
    </div>
  </div>
</template>

<script>
import SlideGenProgress from './SlideGenProgress.vue'
import AgentTracePanel from './AgentTracePanel.vue'

const STAGE_AGENTS = {
  doc_refine: ['doc_extractor'],
  slide_induction: ['schema_extractor'],
  outline: ['planner'],
  slide_gen: ['content_organizer', 'layout_selector', 'editor', 'coder'],
}

export default {
  name: 'StageDetailPanel',
  components: { SlideGenProgress, AgentTracePanel },
  props: {
    stage: { type: Object, default: null },
    taskId: { type: String, required: true },
    slideGen: { type: Object, default: () => ({ slides: [], completed: 0, total: 0 }) },
    stageMessage: { type: String, default: '' },
    liveAgentTrace: { type: Object, default: null },
    liveSlideTraces: { type: Array, default: () => [] },
    downloadLink: { type: String, default: '' },
    filename: { type: String, default: 'final.pptx' },
    awaitingHuman: { type: Object, default: null },
  },
  emits: ['review-submitted'],
  data() {
    return {
      artifactData: {},
      loading: false,
      error: null,
      reviewOutline: [],
      reviewLoading: false,
      reviewSubmitting: false,
      reviewError: '',
      reviewMessage: '',
      finalPreview: {
        loading: false,
        error: '',
        images: [],
      },
      finalLightboxOpen: false,
      finalLightboxIndex: 0,
    }
  },
  mounted() {
    window.addEventListener('keydown', this.handleFinalPreviewKeydown)
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.handleFinalPreviewKeydown)
  },
  computed: {
    stageAgents() {
      if (!this.stage) return []
      if (this.stage.agents?.length) return this.stage.agents
      return STAGE_AGENTS[this.stage.id] || []
    },
    hasAgentTraces() {
      return this.stageAgents.length > 0
    },
    showAgentTraces() {
      if (!this.hasAgentTraces) return false
      if (this.stage.id === 'slide_gen' && this.liveSlideTraces.length > 0) return true
      if (this.stage.id === 'outline' && this.liveAgentTrace) return true
      return false
    },
    hasTechDetails() {
      if (!this.stage) return false
      return (
        (this.stage.inputs?.length > 0) ||
        (this.stage.outputs?.length > 0) ||
        this.stageAgents.length > 0 ||
        this.stage.summary ||
        (this.stage.id === 'pdf_parse' && this.artifactData.source_md)
      )
    },
    isAwaitingOutlineReview() {
      return (
        this.stage?.id === 'outline' &&
        this.stage?.status === 'waiting' &&
        this.awaitingHuman?.type === 'outline'
      )
    },
    isReviewValid() {
      return this.reviewOutline.length > 0 && this.reviewOutline.every(
        (item) => item.purpose?.trim() && item.section?.trim()
      )
    },
    currentFinalPreviewImage() {
      if (!this.finalPreview.images.length) return null
      return this.finalPreview.images[this.finalLightboxIndex] || null
    },
  },
  watch: {
    stage: {
      immediate: true,
      handler(newStage) {
        if (this.isAwaitingOutlineReview) {
          this.loadHumanReview()
        } else if (newStage && newStage.status === 'completed') {
          this.loadArtifacts(newStage.id)
        } else if (!newStage || newStage.status !== 'running') {
          this.artifactData = {}
          this.error = null
        }
      },
    },
    awaitingHuman() {
      if (this.isAwaitingOutlineReview) {
        this.loadHumanReview()
      }
    },
  },
  methods: {
    formatSummary(summary) {
      return JSON.stringify(summary, null, 2)
    },
    truncate(text, len) {
      if (!text) return ''
      return text.length > len ? text.slice(0, len) + '...' : text
    },
    layoutEntries(induction) {
      const entries = {}
      for (const [key, val] of Object.entries(induction)) {
        if (key !== 'functional_keys') entries[key] = val
      }
      return entries
    },
    async loadHumanReview() {
      if (!this.taskId || this.reviewLoading) return
      this.reviewLoading = true
      this.reviewError = ''
      this.reviewMessage = ''
      try {
        const res = await this.$axios.get(`/api/task/${this.taskId}/human-review`)
        this.reviewOutline = (res.data.outline || []).map((item, idx) => ({
          slide: item.slide || idx + 1,
          purpose: item.purpose || '',
          section: item.section || '',
        }))
      } catch (e) {
        this.reviewError = '加载待确认大纲失败：' + (e.response?.data?.detail || e.message)
      } finally {
        this.reviewLoading = false
      }
    },
    async submitOutlineReview() {
      if (!this.isReviewValid || this.reviewSubmitting) return
      this.reviewSubmitting = true
      this.reviewError = ''
      this.reviewMessage = ''
      try {
        await this.$axios.post(
          `/api/task/${this.taskId}/human-review/outline`,
          {
            outline: this.reviewOutline.map((item, idx) => ({
              slide: idx + 1,
              purpose: item.purpose.trim(),
              section: item.section.trim(),
            })),
          }
        )
        this.reviewMessage = '已确认大纲，正在继续生成…'
        this.$emit('review-submitted')
      } catch (e) {
        this.reviewError = '提交失败：' + (e.response?.data?.detail || e.message)
      } finally {
        this.reviewSubmitting = false
      }
    },
    async previewFinalPpt() {
      if (this.finalPreview.loading) return
      this.finalPreview.loading = true
      this.finalPreview.error = ''
      try {
        const previewResp = await this.$axios.post(`/api/task/${this.taskId}/final-preview`)
        const previewId = previewResp.data.preview_id
        const imagesResp = await this.$axios.get(`/api/ppt-preview/${previewId}/images`)
        this.finalPreview.images = imagesResp.data.images || []
      } catch (e) {
        this.finalPreview.images = []
        this.finalPreview.error = e.response?.data?.detail || '最终 PPT 预览生成失败'
      } finally {
        this.finalPreview.loading = false
      }
    },
    openFinalPreviewLightbox(index) {
      if (!this.finalPreview.images.length) return
      this.finalLightboxIndex = index
      this.finalLightboxOpen = true
    },
    closeFinalPreviewLightbox() {
      this.finalLightboxOpen = false
    },
    showFinalPreviewPrev() {
      const total = this.finalPreview.images.length
      if (!total) return
      this.finalLightboxIndex = (this.finalLightboxIndex - 1 + total) % total
    },
    showFinalPreviewNext() {
      const total = this.finalPreview.images.length
      if (!total) return
      this.finalLightboxIndex = (this.finalLightboxIndex + 1) % total
    },
    handleFinalPreviewKeydown(event) {
      if (!this.finalLightboxOpen) return
      if (event.key === 'Escape') {
        this.closeFinalPreviewLightbox()
      } else if (event.key === 'ArrowLeft') {
        this.showFinalPreviewPrev()
      } else if (event.key === 'ArrowRight') {
        this.showFinalPreviewNext()
      }
    },
    async loadArtifacts(stageId) {
      this.loading = true
      this.error = null
      this.artifactData = {}
      const loaders = {
        ppt_parse: ['slide_images', 'image_stats'],
        pdf_parse: ['source_md', 'pdf_images'],
        doc_refine: ['refined_doc'],
        template_prep: ['template_images'],
        slide_induction: ['slide_induction'],
        outline: ['outline'],
        init: ['task'],
      }
      const keys = loaders[stageId]
      if (!keys) {
        this.loading = false
        return
      }
      try {
        const data = {}
        for (const key of keys) {
          if (key === 'source_md') {
            const res = await this.$axios.get(
              `/api/task/${this.taskId}/artifact/${key}`,
              { responseType: 'text' }
            )
            data.source_md = res.data
          } else {
            const res = await this.$axios.get(
              `/api/task/${this.taskId}/artifact/${key}`
            )
            data[key] = res.data
          }
        }
        this.artifactData = data
      } catch (e) {
        this.error = '加载失败：' + (e.response?.data?.detail || e.message)
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style scoped>
.stage-detail-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.empty-state {
  color: var(--color-text-secondary);
  text-align: center;
  padding: 48px 0;
  font-size: 0.9rem;
}

.stage-heading {
  margin: 0 0 16px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
}

.preview-title {
  margin: 0 0 10px;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.detail-section {
  margin-bottom: 14px;
}

.detail-section h4 {
  margin: 0 0 6px;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.detail-section ul {
  margin: 0;
  padding-left: 18px;
  font-size: 0.88rem;
}

.muted {
  color: var(--color-text-secondary);
}

.summary-json,
.md-preview {
  background: var(--color-bg);
  padding: 10px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  overflow: auto;
  max-height: 160px;
  white-space: pre-wrap;
  border: 1px solid var(--color-border);
}

.error-text {
  color: var(--color-error);
  font-size: 0.9rem;
  margin: 0;
}

.success-text {
  color: var(--color-success);
  font-size: 0.9rem;
  margin: 0;
}

.running-hint {
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  margin: 0;
  padding: 10px 12px;
  background: var(--color-primary-light);
  border-radius: var(--radius-sm);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}

.thumb {
  width: 100%;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
}

.section-tree,
.outline-list,
.layout-list {
  font-size: 0.88rem;
  margin: 0;
  padding-left: 18px;
}

.outline-list {
  list-style: decimal;
}

.outline-review {
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: var(--color-primary-light);
  padding: 12px;
}

.outline-editor {
  display: grid;
  gap: 12px;
}

.outline-edit-row {
  display: grid;
  gap: 8px;
  padding: 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.outline-edit-index {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.outline-edit-row label {
  display: grid;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.outline-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  font-size: 0.88rem;
  color: var(--color-text);
  background: var(--color-surface);
}

.outline-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.review-submit {
  justify-self: start;
  padding: 9px 16px;
}

.done-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.done-download,
.done-preview-btn {
  display: inline-block;
  text-decoration: none;
  padding: 10px 24px;
}

.final-preview-message {
  margin-top: 10px;
}

.final-preview-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
}

.final-preview-thumb {
  width: 100%;
  display: block;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: zoom-in;
  background: var(--color-surface);
}

.final-lightbox-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.78);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.final-lightbox-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 6px;
}

.final-lightbox-close {
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

.final-lightbox-nav {
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

.final-lightbox-nav.left {
  left: 16px;
}

.final-lightbox-nav.right {
  right: 16px;
}

.final-lightbox-counter {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 0.85rem;
  margin: 0;
}

.fold-section {
  margin-top: 20px;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  border-top: 1px solid var(--color-border);
  padding-top: 12px;
}

.fold-section summary {
  cursor: pointer;
  user-select: none;
  color: var(--color-text-secondary);
}

.fold-body {
  margin-top: 12px;
}

.agent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-tag {
  padding: 2px 8px;
  background: var(--color-bg);
  color: var(--color-text-secondary);
  border-radius: 12px;
  font-size: 0.75rem;
  font-family: ui-monospace, monospace;
  border: 1px solid var(--color-border);
}

@media (max-width: 768px) {
  .final-lightbox-nav {
    width: 38px;
    height: 38px;
  }
}
</style>
