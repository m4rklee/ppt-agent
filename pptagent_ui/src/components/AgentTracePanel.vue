<template>
  <div :class="['agent-trace-panel', { embedded }]">
    <h4 v-if="!embedded">Agent 输出</h4>
    <p v-if="loading" class="muted">加载 Agent 轨迹...</p>
    <p v-else-if="loadError" class="error-text">{{ loadError }}</p>
    <p v-else-if="!hasContent" class="muted">暂无 Agent 输出记录</p>

    <template v-else>
      <!-- slide_gen: per-slide selector -->
      <div v-if="isSlideGen && perSlide.length" class="slide-selector">
        <label>页码：</label>
        <select v-model.number="selectedSlideIndex">
          <option v-for="slide in perSlide" :key="slide.index" :value="slide.index">
            第 {{ slide.index }} 页 — {{ truncate(slide.purpose, 40) }}
          </option>
        </select>
      </div>

      <div v-for="agentName in activeAgentNames" :key="agentName" class="agent-block">
        <button
          type="button"
          class="agent-header"
          @click="toggleAgent(agentName)"
        >
          <span class="agent-name">{{ agentName }}</span>
          <span class="turn-count">{{ turnCount(agentName) }} 条</span>
          <span class="chevron">{{ expandedAgents[agentName] ? '▼' : '▶' }}</span>
        </button>
        <div v-if="expandedAgents[agentName]" class="turn-list">
          <div
            v-for="(turn, idx) in turnsForAgent(agentName)"
            :key="`${agentName}-${turn.id}-${turn.retry}-${idx}`"
            class="turn-card"
          >
            <div class="turn-meta">
              <span>Turn #{{ turn.id }}</span>
              <span v-if="turn.retry >= 0" class="retry-badge">retry {{ turn.retry }}</span>
              <span v-if="turn.input_tokens" class="token-badge">
                {{ turn.input_tokens }}→{{ turn.output_tokens }} tokens
              </span>
            </div>
            <details class="turn-details">
              <summary>Prompt</summary>
              <pre class="trace-pre">{{ turn.prompt }}</pre>
            </details>
            <details class="turn-details">
              <summary>Response</summary>
              <pre class="trace-pre">{{ formatResponse(turn.response) }}</pre>
            </details>
          </div>
        </div>
      </div>

      <div v-if="codeHistory.length" class="extra-block">
        <button type="button" class="agent-header" @click="showCode = !showCode">
          <span class="agent-name">code_history</span>
          <span class="turn-count">{{ codeHistory.length }} 条</span>
          <span class="chevron">{{ showCode ? '▼' : '▶' }}</span>
        </button>
        <pre v-if="showCode" class="trace-pre">{{ formatJson(codeHistory) }}</pre>
      </div>

      <div v-if="apiHistory.length" class="extra-block">
        <button type="button" class="agent-header" @click="showApi = !showApi">
          <span class="agent-name">api_history</span>
          <span class="turn-count">{{ apiHistory.length }} 条</span>
          <span class="chevron">{{ showApi ? '▼' : '▶' }}</span>
        </button>
        <pre v-if="showApi" class="trace-pre">{{ formatJson(apiHistory) }}</pre>
      </div>
    </template>
  </div>
</template>

<script>
const STAGE_TRACE_FILES = {
  doc_refine: 'doc_extractor',
  slide_induction: 'schema_extractor',
  outline: 'planner',
  slide_gen: 'slide_gen',
}

export default {
  name: 'AgentTracePanel',
  props: {
    taskId: { type: String, required: true },
    stageId: { type: String, required: true },
    agentNames: { type: Array, default: () => [] },
    liveTrace: { type: Object, default: null },
    liveSlideTraces: { type: Array, default: () => [] },
    embedded: { type: Boolean, default: false },
  },
  data() {
    return {
      traceData: null,
      loading: false,
      loadError: null,
      expandedAgents: {},
      selectedSlideIndex: 1,
      showCode: false,
      showApi: false,
    }
  },
  computed: {
    isSlideGen() {
      return this.stageId === 'slide_gen'
    },
    perSlide() {
      if (this.liveSlideTraces?.length) {
        return [...this.liveSlideTraces].sort((a, b) => a.index - b.index)
      }
      return this.traceData?.per_slide || []
    },
    activeSlideTrace() {
      if (!this.isSlideGen) return null
      const traces = this.perSlide
      if (!traces.length) return null
      return traces.find((s) => s.index === this.selectedSlideIndex) || traces[0]
    },
    activeAgentNames() {
      if (this.isSlideGen && this.activeSlideTrace?.agents) {
        return Object.keys(this.activeSlideTrace.agents)
      }
      if (this.agentNames.length) return this.agentNames
      if (this.traceData?.agents) return Object.keys(this.traceData.agents)
      if (this.liveTrace?.turns || this.traceData?.turns) {
        return this.agentNames.length ? this.agentNames : ['agent']
      }
      return []
    },
    codeHistory() {
      if (this.isSlideGen && this.activeSlideTrace) {
        return this.activeSlideTrace.code_history || []
      }
      return this.traceData?.code_history || []
    },
    apiHistory() {
      if (this.isSlideGen && this.activeSlideTrace) {
        return this.activeSlideTrace.api_history || []
      }
      return this.traceData?.api_history || []
    },
    hasContent() {
      if (this.liveTrace || this.liveSlideTraces?.length) return true
      if (!this.traceData) return false
      if (this.traceData.turns?.length) return true
      if (this.traceData.agents && Object.keys(this.traceData.agents).length) return true
      if (this.traceData.per_slide?.length) return true
      return false
    },
  },
  watch: {
    stageId: { immediate: true, handler() { this.loadTrace() } },
    liveTrace: { deep: true, handler(val) { if (val) this.traceData = null } },
    perSlide: {
      handler(slides) {
        if (slides.length && !slides.find((s) => s.index === this.selectedSlideIndex)) {
          this.selectedSlideIndex = slides[0].index
        }
      },
      immediate: true,
    },
  },
  methods: {
    truncate(text, len) {
      if (!text) return ''
      return text.length > len ? text.slice(0, len) + '...' : text
    },
    formatResponse(response) {
      if (typeof response !== 'string') return this.formatJson(response)
      try {
        const parsed = JSON.parse(response)
        return JSON.stringify(parsed, null, 2)
      } catch {
        return response
      }
    },
    formatJson(data) {
      return JSON.stringify(data, null, 2)
    },
    toggleAgent(name) {
      this.expandedAgents[name] = !this.expandedAgents[name]
    },
    turnCount(agentName) {
      return this.turnsForAgent(agentName).length
    },
    turnsForAgent(agentName) {
      const simpleTurns = this.liveTrace?.turns || this.traceData?.turns
      if (simpleTurns && (agentName === 'agent' || this.agentNames.includes(agentName))) {
        return simpleTurns
      }
      if (this.isSlideGen && this.activeSlideTrace?.agents?.[agentName]) {
        return this.activeSlideTrace.agents[agentName]
      }
      return this.traceData?.agents?.[agentName] || []
    },
    async loadTrace() {
      this.loadError = null
      if (this.liveTrace || this.liveSlideTraces?.length) return
      const traceFile = STAGE_TRACE_FILES[this.stageId]
      if (!traceFile) {
        this.traceData = null
        return
      }
      this.loading = true
      try {
        const res = await this.$axios.get(
          `/api/task/${this.taskId}/agent-traces/${traceFile}`
        )
        this.traceData = res.data
        for (const name of this.activeAgentNames) {
          this.expandedAgents[name] = false
        }
      } catch (e) {
        if (e.response?.status === 404) {
          this.traceData = null
        } else {
          this.loadError = '加载 Agent 轨迹失败: ' + (e.response?.data?.detail || e.message)
        }
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style scoped>
.agent-trace-panel {
  margin-top: 16px;
  border-top: 1px solid var(--color-border);
  padding-top: 12px;
}

.agent-trace-panel.embedded {
  margin-top: 0;
  border-top: none;
  padding-top: 0;
}

.agent-trace-panel h4 {
  margin: 0 0 10px;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.muted {
  color: var(--color-text-secondary);
  font-size: 0.85em;
}

.error-text {
  color: var(--color-error);
  font-size: 0.85em;
}

.slide-selector {
  margin-bottom: 12px;
  font-size: 0.85em;
}

.slide-selector select {
  margin-left: 6px;
  max-width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.agent-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.85em;
  text-align: left;
}

.agent-name {
  font-weight: 500;
  color: var(--color-text);
  flex: 1;
  font-family: ui-monospace, monospace;
  font-size: 0.9em;
}

.turn-count {
  color: var(--color-text-secondary);
  font-size: 0.9em;
}

.chevron {
  color: var(--color-text-secondary);
  font-size: 0.75em;
}

.turn-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin-bottom: 8px;
  background: var(--color-bg);
}

.turn-meta {
  display: flex;
  gap: 8px;
  font-size: 0.78em;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}

.retry-badge {
  color: var(--color-warning);
}

.token-badge {
  color: var(--color-primary);
}

.turn-details {
  margin-bottom: 4px;
  font-size: 0.82em;
}

.turn-details summary {
  cursor: pointer;
  color: var(--color-text-secondary);
  user-select: none;
}

.trace-pre {
  background: var(--color-surface);
  padding: 8px;
  border-radius: var(--radius-sm);
  font-size: 0.75em;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 4px 0 0;
  border: 1px solid var(--color-border);
}
</style>
