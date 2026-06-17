<template>
  <div class="generate-container">
    <header class="page-header">
      <div class="header-row">
        <div class="status-block">
          <div class="progress-wrap">
            <progress :value="progress" max="100" class="progress-bar"></progress>
            <span class="progress-pct">{{ progress }}%</span>
          </div>
          <p class="status-message">{{ displayStatus }}</p>
        </div>
        <button type="button" class="btn-outline new-task-btn" @click="goToNewTask">
          新建任务
        </button>
      </div>
    </header>

    <div v-if="downloadLink" class="download-banner">
      <a :href="downloadLink" :download="filename" class="btn-primary download-btn">
        下载 PPTX
      </a>
    </div>

    <div class="main-layout">
      <aside class="timeline-col">
        <PipelineTimeline
          :stages="timelineStages"
          :elapsed-ms="elapsedMs"
          :selected-id="selectedStageId"
          @select="onSelectStage"
        />
      </aside>
      <main class="detail-col">
        <StageDetailPanel
          :stage="selectedStage"
          :task-id="taskId"
          :slide-gen="slideGen"
          :stage-message="stageMessageForSelected"
          :live-agent-trace="liveAgentTrace"
          :live-slide-traces="liveSlideTraces"
          :download-link="downloadLink"
          :filename="filename"
          :awaiting-human="awaitingHuman"
          @review-submitted="handleReviewSubmitted"
        />
      </main>
    </div>

    <footer class="page-footer"></footer>
  </div>
</template>

<script>
import PipelineTimeline from './PipelineTimeline.vue'
import StageDetailPanel from './StageDetailPanel.vue'

const DEFAULT_STAGES = [
  { id: 'init', label: '任务初始化', inputs: ['上传 PDF/PPTX', '目标页数'], outputs: ['task.json'], status: 'pending' },
  { id: 'ppt_parse', label: '参考 PPT 解析', inputs: ['source.pptx'], outputs: ['slide_images/', 'image_stats.json'], status: 'pending' },
  { id: 'pdf_parse', label: 'PDF 解析', inputs: ['source.pdf'], outputs: ['source.md', 'meta.json'], status: 'pending' },
  { id: 'doc_refine', label: '文档结构化', inputs: ['source.md'], outputs: ['refined_doc.json'], agents: ['doc_extractor'], status: 'pending' },
  { id: 'template_prep', label: '版式模板图', inputs: ['presentation 布局结构'], outputs: ['template.pptx', 'template_images/'], agents: [], status: 'pending' },
  { id: 'slide_induction', label: '模板分析', inputs: ['slide_images', 'template_images'], outputs: ['slide_induction.json'], agents: ['schema_extractor'], status: 'pending' },
  { id: 'outline', label: '大纲生成', inputs: ['refined_doc.json', 'slide_induction.json'], outputs: ['outline.json'], agents: ['planner'], status: 'pending' },
  { id: 'slide_gen', label: '逐页生成', inputs: ['outline.json', '参考模板'], outputs: ['各页 SlidePage'], agents: ['content_organizer', 'layout_selector', 'editor', 'coder'], status: 'pending' },
  { id: 'done', label: '完成', inputs: [], outputs: ['final.pptx'], status: 'pending' },
]

export default {
  name: 'GenerateComponent',
  components: { PipelineTimeline, StageDetailPanel },
  data() {
    return {
      progress: 0,
      statusMessage: '正在连接…',
      downloadLink: '',
      taskId: history.state.taskId,
      filename: 'final.pptx',
      socket: null,
      elapsedMs: 0,
      elapsedTimer: null,
      elapsedBaseMs: 0,
      elapsedBaseAt: null,
      timelineStages: DEFAULT_STAGES.map((s) => ({ ...s })),
      selectedStageId: null,
      slideGen: { slides: [], completed: 0, total: 0, current_purpose: '' },
      stageMessage: '',
      stageMessageStageId: null,
      liveAgentTrace: null,
      liveSlideTraces: [],
      awaitingHuman: null,
      isDone: false,
      elapsedFrozen: false,
    }
  },
  computed: {
    selectedStage() {
      if (!this.selectedStageId) {
        const running = this.timelineStages.find((s) => s.status === 'running')
        if (running) return running
        const lastCompleted = [...this.timelineStages].reverse().find((s) => s.status === 'completed')
        return lastCompleted || null
      }
      return this.timelineStages.find((s) => s.id === this.selectedStageId) || null
    },
    stageMessageForSelected() {
      const stage = this.selectedStage
      if (!stage || stage.status !== 'running') return ''
      if (this.stageMessageStageId && stage.id !== this.stageMessageStageId) return ''
      return this.stageMessage
    },
    displayStatus() {
      return this.statusMessage
    },
  },
  async created() {
    await this.loadPipelineState()
    this.startGeneration()
  },
  beforeUnmount() {
    this.closeSocket()
    this.stopElapsedTimer()
  },
  methods: {
    goToNewTask() {
      const running = this.timelineStages.some((s) => s.status === 'running')
      if (running && !this.isDone) {
        const confirmed = window.confirm('任务仍在进行中，确认返回并新建任务吗？')
        if (!confirmed) return
      }
      this.closeSocket()
      this.$router.push({ name: 'Upload' })
    },
    formatStageStatus(status) {
      const map = {
        pending: '等待',
        running: '进行中',
        completed: '完成',
        failed: '失败',
        waiting: '待确认',
      }
      return map[status] || status
    },
    onSelectStage(stageId) {
      this.selectedStageId = stageId
    },
    applyPipeline(pipeline) {
      if (!pipeline || !pipeline.stages) return
      this.awaitingHuman = pipeline.awaiting_human || null
      this.timelineStages = DEFAULT_STAGES.map((def) => {
        const fromState = pipeline.stages[def.id] || {}
        return {
          ...def,
          status: fromState.status || 'pending',
          elapsed_ms: fromState.elapsed_ms,
          summary: fromState.summary,
          cached: fromState.cached,
          agents: fromState.agents || def.agents || [],
        }
      })
      if (pipeline.slide_gen) {
        this.slideGen = {
          slides: pipeline.slide_gen.slides || [],
          completed: pipeline.slide_gen.completed || 0,
          total: pipeline.slide_gen.total || 0,
          current_purpose: pipeline.slide_gen.current_purpose || '',
        }
      }
      const allDone = this.timelineStages.find((s) => s.id === 'done')?.status === 'completed'
      const failedStage = this.timelineStages.find((s) => s.status === 'failed')

      if (allDone) {
        const doneSummary = pipeline.stages?.done?.summary || {}
        const finalMs = doneSummary.total_elapsed_ms ?? pipeline.elapsed_ms ?? this.elapsedMs
        this.freezeElapsed(finalMs)
        this.isDone = true
        this.progress = 100
        this.selectedStageId = 'done'
        this.statusMessage = '生成完成'
        this.stageMessage = ''
        if (!this.downloadLink) {
          this.fetchDownloadLink()
        }
      } else if (failedStage) {
        this.freezeElapsed(pipeline.elapsed_ms ?? this.elapsedMs)
        this.statusMessage = `${failedStage.label} 失败`
        this.selectedStageId = failedStage.id
      } else {
        if (pipeline.elapsed_ms != null && !this.elapsedFrozen) {
          this.syncElapsed(pipeline.elapsed_ms)
        }
        const running = this.timelineStages.find((s) => s.status === 'running')
        if (running) {
          this.selectedStageId = running.id
        } else {
          const waiting = this.timelineStages.find((s) => s.status === 'waiting')
          if (waiting) {
            this.selectedStageId = waiting.id
            this.statusMessage = '等待确认大纲'
          }
        }
      }
    },
    syncElapsed(serverMs) {
      if (this.elapsedFrozen) return
      this.elapsedBaseMs = serverMs
      this.elapsedBaseAt = Date.now()
      this.elapsedMs = serverMs
      if (!this.elapsedTimer) {
        this.elapsedTimer = setInterval(() => {
          if (this.elapsedBaseAt != null && !this.elapsedFrozen) {
            this.elapsedMs = this.elapsedBaseMs + (Date.now() - this.elapsedBaseAt)
          }
        }, 1000)
      }
    },
    freezeElapsed(finalMs) {
      this.stopElapsedTimer()
      this.elapsedFrozen = true
      this.elapsedBaseAt = null
      if (finalMs != null) {
        this.elapsedMs = finalMs
        this.elapsedBaseMs = finalMs
      }
    },
    stopElapsedTimer() {
      if (this.elapsedTimer) {
        clearInterval(this.elapsedTimer)
        this.elapsedTimer = null
      }
    },
    async loadPipelineState() {
      if (!this.taskId) return
      try {
        const res = await this.$axios.get(`/api/task/${this.taskId}/pipeline`)
        this.applyPipeline(res.data)
      } catch (e) {
        console.warn('Failed to load pipeline state', e)
      }
    },
    async startGeneration() {
      if (!this.taskId) {
        this.statusMessage = '未找到任务，请先上传文件'
        return
      }
      console.log('Connecting to websocket', `/wsapi/${this.taskId}`)
      this.socket = new WebSocket(`/wsapi/${this.taskId}`)

      this.socket.onmessage = (event) => {
        const data = JSON.parse(event.data)
        this.handlePipelineEvent(data)
      }
      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error)
        this.statusMessage = '连接失败，请刷新页面重试'
        this.freezeElapsed(this.elapsedMs)
        this.closeSocket()
      }
    },
    handlePipelineEvent(data) {
      this.progress = data.progress
      if (data.subprogress?.message) {
        this.statusMessage = `${data.status} — ${data.subprogress.message}`
      } else if (data.stage_status) {
        this.statusMessage = `${data.status}（${this.formatStageStatus(data.stage_status)}）`
      } else {
        this.statusMessage = data.status || this.statusMessage
      }

      if (data.stage_status === 'failed') {
        if (data.pipeline) {
          this.applyPipeline(data.pipeline)
        } else if (data.stage_id) {
          const idx = this.timelineStages.findIndex((s) => s.id === data.stage_id)
          if (idx >= 0) {
            this.timelineStages[idx].status = 'failed'
            if (data.summary) this.timelineStages[idx].summary = data.summary
          }
        }
        if (data.elapsed_ms != null) {
          this.freezeElapsed(data.elapsed_ms)
        }
        this.selectedStageId = data.stage_id
        this.stageMessage = data.summary?.error || ''
        this.closeSocket()
        return
      }

      if (data.elapsed_ms != null && !this.elapsedFrozen) {
        this.syncElapsed(data.elapsed_ms)
      }

      if (data.pipeline) {
        this.applyPipeline(data.pipeline)
      } else if (data.stage_id) {
        const idx = this.timelineStages.findIndex((s) => s.id === data.stage_id)
        if (idx >= 0) {
          this.timelineStages[idx].status = data.stage_status
          if (data.summary) this.timelineStages[idx].summary = data.summary
          if (data.stage_elapsed_ms != null) {
            this.timelineStages[idx].elapsed_ms = data.stage_elapsed_ms
          }
        }
      }

      if (data.subprogress) {
        if (data.subprogress.message) {
          this.stageMessage = data.subprogress.message
          this.stageMessageStageId = data.stage_id
          this.statusMessage = data.status + ' — ' + data.subprogress.message
        }
        if (data.subprogress.agent_trace) {
          if (data.stage_id === 'outline') {
            this.liveAgentTrace = data.subprogress.agent_trace
          } else if (data.stage_id === 'slide_gen') {
            if (data.subprogress.live_traces) {
              this.liveSlideTraces = data.subprogress.live_traces
            } else {
              const idx = this.liveSlideTraces.findIndex(
                (t) => t.index === data.subprogress.agent_trace.index
              )
              if (idx >= 0) {
                this.liveSlideTraces.splice(idx, 1, data.subprogress.agent_trace)
              } else {
                this.liveSlideTraces.push(data.subprogress.agent_trace)
              }
              this.liveSlideTraces.sort((a, b) => a.index - b.index)
            }
          }
        }
        if (data.stage_id === 'slide_gen' && (data.subprogress.slides || data.subprogress.total)) {
          this.slideGen = {
            slides: data.subprogress.slides || [],
            completed: data.subprogress.completed || 0,
            total: data.subprogress.total || 0,
            current_purpose: data.subprogress.current_purpose || '',
          }
          if (!this.isDone) {
            this.selectedStageId = 'slide_gen'
          }
        } else if (data.stage_id && !this.isDone) {
          this.selectedStageId = data.stage_id
        }
      } else if (data.stage_status === 'running' && data.stage_id && !this.isDone) {
        this.selectedStageId = data.stage_id
        if (data.stage_id !== this.stageMessageStageId) {
          this.stageMessage = ''
          this.stageMessageStageId = null
        }
      }

      if (data.stage_id === 'done' && data.stage_status === 'completed') {
        const finalMs =
          data.summary?.total_elapsed_ms ?? data.elapsed_ms ?? this.elapsedMs
        this.freezeElapsed(finalMs)
        if (!this.isDone) {
          this.isDone = true
          this.progress = 100
          this.selectedStageId = 'done'
          this.statusMessage = '生成完成'
          this.stageMessage = ''
          this.closeSocket()
          this.fetchDownloadLink()
        }
      }
    },
    async fetchDownloadLink() {
      try {
        const downloadResponse = await this.$axios.get('/api/download', {
          params: { task_id: this.taskId },
          responseType: 'blob',
        })
        this.downloadLink = URL.createObjectURL(downloadResponse.data)
        this.filename = 'ppagent_' + this.taskId.replace('/', '_') + '.pptx'
      } catch (error) {
        console.error('Download error:', error)
        this.statusMessage += '，下载失败'
      }
    },
    async handleReviewSubmitted() {
      this.statusMessage = '大纲已确认，正在继续生成…'
      await this.loadPipelineState()
    },
    closeSocket() {
      if (this.socket) {
        this.socket.close()
        this.socket = null
      }
    },
  },
}
</script>

<style scoped>
.generate-container {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 48px);
  padding: 20px 24px 32px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
}

.page-header {
  margin-bottom: 16px;
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.status-block {
  flex: 1;
  min-width: 0;
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.progress-bar {
  flex: 1;
  height: 4px;
  appearance: none;
  border: none;
  border-radius: 2px;
  background: var(--color-border);
}

.progress-bar::-webkit-progress-bar {
  background: var(--color-border);
  border-radius: 2px;
}

.progress-bar::-webkit-progress-value {
  background: var(--color-primary);
  border-radius: 2px;
}

.progress-pct {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}

.status-message {
  font-size: 0.95rem;
  color: var(--color-text);
  margin: 0;
  line-height: 1.4;
}

.new-task-btn {
  flex-shrink: 0;
  width: auto;
  white-space: nowrap;
  padding: 8px 14px;
}

.download-banner {
  margin-bottom: 16px;
}

.download-btn {
  width: 100%;
  padding: 12px;
  font-size: 1rem;
}

.main-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  flex: 1;
  min-height: 400px;
}

.timeline-col,
.detail-col {
  min-height: 400px;
}

.page-footer {
  margin-top: 24px;
  min-height: 1px;
}

@media (max-width: 768px) {
  .generate-container {
    padding: 16px;
  }

  .main-layout {
    grid-template-columns: 1fr;
  }

  .header-row {
    flex-direction: column;
  }
}
</style>
