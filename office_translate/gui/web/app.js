const { createApp } = Vue;

const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

function looksMaskedApiKey(value) {
  return /(?:\*{2,}|•{2,}|…|\.\.\.)/.test(value || '');
}

function maskApiKey(value) {
  if (typeof value !== 'string' || !value) return '';
  if (looksMaskedApiKey(value)) return value;
  if (value.length <= 8) return '••••••••';
  return value.slice(0, 3) + '••••' + value.slice(-4);
}

// Settings responses are untrusted from the browser's point of view.  Keep only
// the server-provided masked/configured representation in Vue state; a secret
// returned under an unexpected field is deliberately discarded.
function normalizeSettingsForUi(raw) {
  const root = raw && typeof raw === 'object' ? raw : {};
  const rawAi = root.ai && typeof root.ai === 'object' ? root.ai : {};
  const rawProviders = rawAi.providers && typeof rawAi.providers === 'object'
    ? rawAi.providers
    : {};
  const providers = {};
  Object.entries(rawProviders).forEach(([key, value]) => {
    const provider = value && typeof value === 'object' ? value : {};
    const returnedMask = provider.api_key_masked
      || provider.masked_api_key
      || provider.api_key_display
      || '';
    const configuredFlag = provider.api_key_configured
      ?? provider.has_api_key
      ?? provider.api_key_set
      ?? provider.secret_configured;
    providers[key] = {
      ...provider,
      api_key: '',
      api_key_masked: maskApiKey(returnedMask),
      api_key_configured: configuredFlag === undefined
        ? Boolean(returnedMask)
        : Boolean(configuredFlag),
    };
  });
  return {
    ...root,
    ai: {
      engine: 'google',
      active_provider: 'openai',
      mirrors: [],
      source_lang: 'en',
      target_lang: 'zh-CN',
      concurrency: 4,
      ...rawAi,
      providers,
    },
  };
}

createApp({
  data() {
    return {
      view: 'workflow',
      steps: ['任务', '提取', '翻译', '审核', '导出'],
      step: 0,
      jobs: [],
      currentJob: null,
      newJobInput: '',
      newJobName: '',
      extracting: false,
      extractInfo: null,
      sourceItems: [],
      sourceTexts: [],
      sourceText: '',
      currentSourceRevision: null,
      currentTranslationRevision: null,
      jobRequestToken: 0,
      translateMode: 'ai',
      manualTranslations: '',
      manualItems: [],
      manualPasteDirty: false,
      editingManualRow: null,
      manualLoadedOnce: false,
      manualError: '',
      engine: 'google',
      activeProviderKey: 'openai',
      activeModel: 'gpt-4o-mini',
      uploadingFile: false,
      translating: false,
      currentOperationId: null,
      translateProgress: 0,
      translateTotal: 0,
      translateDone: 0,
      translateChunks: 0,
      translateThinking: {},
      translatePreviews: {},      // id → 流式已解析片段（仅预览，最终以正式结果为准）
      translateAutoScroll: true,  // 翻译列表接近底部时自动跟随
      thinkingAutoScroll: true,   // 思考面板接近底部时自动跟随
      translateResults: [],
      operationSummary: null,
      translateDiagnostics: [],
      translateSources: [],       // 待译原文（与 translateResults 按 id 对应）
      translateBlocksList: [],    // 每块首行号（meta 下发）
      translateBlocks: [],        // 已完成的思考块 [{base, text}]
      translateBlockSaved: new Set(),
      translateDiagnosticSaved: new Set(),
      selectedTermFilter: null,   // 右侧术语筛选（null=全部）
      editingRow: null,           // 正在编辑译文的行 id
      translateElapsed: 0,        // 翻译耗时（秒）
      translateQuery: '',         // 工作区搜索
      failedRows: [],             // 翻译失败的行 id
      retryingFailed: false,
      glossaryCategories: [],
      selectedCategories: [],
      // Review is the single client-side source of truth for decisions.  The
      // server contract is documented in loadReview()/saveReview(); do not
      // derive a second mutable pending list from it.
      reviewItems: [],
      reviewState: 'idle',
      reviewError: '',
      reviewSaveState: 'idle',
      reviewSaveError: '',
      reviewRevision: null,
      translated: false,
      applying: false,
      applyInfo: null,
      applyError: '',
      richTextPolicy: 'flatten',
      translatedTxt: '',
      toasts: [],
      toastSeq: 0,
      modal: null,
      modalSeq: 0,
      lastDiagnostic: null,
      jobsState: 'idle',
      jobsError: '',
      settingsState: 'idle',
      settingsError: '',
      glossaryState: 'idle',
      glossaryError: '',
      mirrorsState: 'idle',
      mirrorsError: '',
      translateError: '',
      // 术语库管理
      glossaryCategoryFilter: '',
      showAddTerm: false,
      newTerm: {category: '', source: '', target: '', note: ''},
      glossaryDetail: {},
      // 设置
      settings: {ai: {engine: 'google', providers: {}, active_provider: 'openai', mirrors: [], source_lang: 'en', target_lang: 'zh-CN', concurrency: 4}},
      mirrorsText: '',
      customMirrors: null,
      testingMirrors: false,
      mirrorTestResults: [],
      // OpenRouter 模型拉取
      openrouterLoading: false,
      openrouterModels: [],
      expandedModel: '',  // "providerKey/modelName"，当前展开的模型（默认收起）
      pendingApiKeys: {},           // 仅保存用户本次输入；请求完成后立即清除
      providerTestResults: {},      // 供应商 key → 测试结果
      testingProvider: '',          // 正在测试的供应商 key
    };
  },
  computed: {
    filteredGlossary() {
      const cats = this.glossaryDetail.categories || {};
      const names = Object.keys(cats).sort();
      const filtered = this.glossaryCategoryFilter ? [this.glossaryCategoryFilter] : names;
      return filtered.filter(n => cats[n]).map(name => ({name, entries: cats[name]}));
    },
    // 当前供应商的模型列表（由 model_configs 键驱动）
    activeProviderModels() {
      return this.providerModelNames(this.activeProviderKey);
    },
    // 批量粘贴只负责初始化，逐条结构化结果才是真相源
    manualMappings() {
      const targets = new Map(this.manualItems.map(item => [item.id, item.translation]));
      return this.sourceTexts.map((src, i) => ({id: i, source: src, target: targets.get(i) || ''}));
    },
    // 批量粘贴按物理行初始化；逐条编辑可安全包含内部换行
    manualLineStatus() {
      const lines = this.manualPasteDirty
        ? (this.manualTranslations === '' ? [] : this.manualTranslations.split('\n'))
        : this.manualItems.map(item => item.translation);
      const expected = this.sourceTexts.length;
      const count = lines.length;
      const diff = count - expected;
      let missing = '';
      if (diff < 0) {
        const missingRows = [];
        for (let i = 0; i < expected; i++) {
          if (i >= count || (lines[i] || '').trim() === '') missingRows.push(i + 1);
        }
        missing = missingRows.join('、');
      }
      return {count, expected, diff, missing};
    },
    manualBatchSafe() {
      return this.sourceTexts.every(text => !text.includes('\n') && !text.includes('\r'));
    },
    manualEmptyRows() {
      return this.sourceTexts
        .map((_, id) => this.manualItems.find(item => item.id === id))
        .map((item, id) => ({id, translation: item ? item.translation : ''}))
        .filter(item => item.translation.trim() === '');
    },
    pendingReviews() {
      return this.reviewItems.filter(item => item.decision === 'pending');
    },
    pendingTerms() {
      return this.pendingReviews.filter(item => item.kind === 'term');
    },
    pendingBlankTranslations() {
      return this.pendingReviews.filter(item => item.kind === 'blank_translation');
    },
    unconfirmedBlankTranslations() {
      return this.reviewItems.filter(item => item.kind === 'blank_translation' && !item.empty_translation_confirmed);
    },
    decidedReviews() {
      return this.reviewItems.filter(item => item.decision !== 'pending');
    },
    reviewReady() {
      return this.reviewState === 'ready'
        && this.pendingReviews.length === 0
        && this.unconfirmedBlankTranslations.length === 0;
    },
    // 逐行对照映射：原文 + 译文（正式结果优先，翻译中显示已解析的预览片段）
    translateRows() {
      return this.translateSources.map((src, i) => {
        const r = this.translateResults.find(x => x.id === i);
        const preview = this.translatePreviews[i];
        return {
          id: i,
          source: src,
          translation: r ? r.translation : (preview ? preview.translation : ''),
          uncertain: r ? (r.uncertain_terms || []) : (preview ? (preview.uncertain_terms || []) : []),
          finalized: !!r,
          previewing: !r && !!preview,
        };
      });
    },
    // 翻译中只显示已出现结果的行（正式或预览），按原文顺序排列
    visibleTranslateRows() {
      if (!this.translating) return this.filteredTranslateRows;
      const visible = this.translateRows.filter(r => r.finalized || r.previewing);
      if (this.selectedTermFilter) {
        return visible.filter(r => r.uncertain.some(t => t.term === this.selectedTermFilter));
      }
      return visible;
    },
    // 术语筛选后的行
    filteredTranslateRows() {
      let rows = this.translateRows;
      if (this.selectedTermFilter) rows = rows.filter(r => r.uncertain.some(t => t.term === this.selectedTermFilter));
      if (this.translateQuery) {
        const q = this.translateQuery.toLowerCase();
        rows = rows.filter(r => (r.source || '').toLowerCase().includes(q) || (r.translation || '').toLowerCase().includes(q));
      }
      return rows;
    },
    translateElapsedText() {
      const s = this.translateElapsed;
      return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    },
    // 不确定术语聚合：term → {term, reason, candidate, rows}
    termAggregates() {
      const map = {};
      for (const r of this.translateResults) {
        for (const t of (r.uncertain_terms || [])) {
          if (!t.term) continue;
          if (!map[t.term]) map[t.term] = {term: t.term, reason: t.reason, candidate: t.candidate, rows: []};
          map[t.term].rows.push(r.id);
        }
      }
      return Object.values(map)
        .map(v => ({...v, count: v.rows.length}))
        .sort((a, b) => b.count - a.count);
    },
    // 翻译中正在思考的块（thinking 增量实时显示）
    activeThinkingText() {
      const keys = Object.keys(this.translateThinking);
      return keys.length ? this.translateThinking[keys[keys.length - 1]] : '';
    },
    thinkingCount() {
      return this.translateBlocks.length + (this.translating && this.activeThinkingText ? 1 : 0);
    },
    canExport() {
      return !!(
        this.translated
        && this.operationSummary
        && this.operationSummary.status === 'succeeded'
        && this.operationSummary.total === this.translateResults.length
        && this.failedRows.length === 0
        && this.reviewReady
        && !['saving', 'error'].includes(this.reviewSaveState)
      );
    },
    exportBlockReason() {
      if (!this.translated || !this.operationSummary) return '翻译结果尚未完整保存。';
      if (this.operationSummary.status !== 'succeeded' || this.failedRows.length) return '仍有失败、取消或未完成的翻译条目。';
      if (this.operationSummary.total !== this.translateResults.length) return '翻译 summary 与结果条数不一致。';
      if (this.reviewState === 'loading') return '审核记录仍在恢复。';
      if (this.reviewState === 'error') return '审核记录加载失败，请先恢复审核状态。';
      if (this.unconfirmedBlankTranslations.length) return `仍有 ${this.unconfirmedBlankTranslations.length} 条空译文未确认。`;
      if (this.pendingReviews.length) return `仍有 ${this.pendingReviews.length} 个审核项未处理。`;
      if (this.reviewSaveState === 'error') return '审核决定尚未成功保存。';
      return '';
    },
    applyDownloads() {
      if (!this.applyInfo) return [];
      const items = [];
      if (this.applyInfo.translated_output) {
        items.push({
          kind: 'translated', label: '仅译文版',
          path: this.applyInfo.translated_output,
          url: `/api/jobs/${this.currentJob}/download?kind=translated`,
          filename: (this.applyInfo.translated_output || '').split('/').pop(),
        });
      }
      if (this.applyInfo.bilingual_output) {
        items.push({
          kind: 'bilingual', label: '原文-译文对照版',
          path: this.applyInfo.bilingual_output,
          url: `/api/jobs/${this.currentJob}/download?kind=bilingual`,
          filename: (this.applyInfo.bilingual_output || '').split('/').pop(),
        });
      }
      return items;
    },
  },
  methods: {
    recordDiagnostic(operation, error) {
      this.lastDiagnostic = {
        time: new Date().toISOString(),
        job: this.currentJob || null,
        operation,
        error_code: (error && error.code) || 'client_error',
      };
    },
    async copyDiagnostic() {
      if (!this.lastDiagnostic) return;
      const text = JSON.stringify(this.lastDiagnostic, null, 2);
      try {
        await navigator.clipboard.writeText(text);
        this.toast('诊断信息已复制', 'success');
      } catch (e) {
        this.toast('复制诊断信息失败', 'error');
      }
    },
    toast(msg, type) {
      if (!type) {
        if (/失败|错误|异常/.test(msg)) type = 'error';
        else if (/至少|请|尚未|暂无|不能|缺少|无效|核对|为空/.test(msg)) type = 'warn';
        else if (/成功|完成|已/.test(msg)) type = 'success';
        else type = 'info';
      }
      const icons = { success: '✓', error: '✕', warn: '⚠', info: 'ℹ' };
      const id = ++this.toastSeq;
      this.toasts.push({ id, msg, type, icon: icons[type] || icons.info });
      setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 3000);
    },
    confirmModal({ title = '确认', message = '', danger = false, okText = '确定' } = {}) {
      return new Promise((resolve) => {
        this.modal = {
          kind: 'confirm', id: 'modal-' + (++this.modalSeq), title, message, danger, okText,
          _resolve: resolve, _previousFocus: document.activeElement,
        };
        this.focusModal();
      });
    },
    formModal({ title = '', fields = [], okText = '确定', danger = false, validate = null } = {}) {
      return new Promise((resolve) => {
        this.modal = {
          kind: 'form', id: 'modal-' + (++this.modalSeq), title, fields: fields.map(f => ({ ...f })), okText, danger,
          validate, error: '', _resolve: resolve, _previousFocus: document.activeElement,
        };
        this.focusModal();
      });
    },
    richTextPolicyModal() {
      const options = [
        {
          value: 'preserve_original',
          title: '保留受影响单元格的原文',
          description: '这些源单元格保持原文和局部格式，不写入译文；其他单元格正常导出。',
        },
        {
          value: 'flatten',
          title: '明确转为纯文本译文',
          description: '用纯文本译文替换整个富文本单元格，单元格内的局部字体、颜色等格式会丢失。',
        },
      ];
      return new Promise((resolve) => {
        this.modal = {
          kind: 'rich-text-policy',
          id: 'modal-' + (++this.modalSeq),
          title: '选择富文本处理方式',
          value: this.richTextPolicy,
          options,
          okText: '保存处理方式',
          wide: true,
          _resolve: resolve,
          _previousFocus: document.activeElement,
        };
        this.focusModal();
      });
    },
    focusModal() {
      this.$nextTick(() => {
        const root = this.$refs.modalBox;
        if (!root) return;
        const target = root.querySelector('[data-modal-autofocus]')
          || root.querySelector('input, textarea, select, button');
        if (target) target.focus();
      });
    },
    restoreModalFocus(previousFocus) {
      this.$nextTick(() => {
        if (previousFocus && typeof previousFocus.focus === 'function' && document.contains(previousFocus)) {
          previousFocus.focus();
        }
      });
    },
    modalOk() {
      if (!this.modal) return;
      const m = this.modal;
      if (m.kind === 'form' && m.validate) {
        const err = m.validate(m.fields);
        if (err) { m.error = err; return; }
      }
      const resolve = m._resolve;
      this.modal = null;
      this.restoreModalFocus(m._previousFocus);
      if (m.kind === 'confirm') resolve(true);
      else if (m.kind === 'rich-text-policy') resolve(m.value);
      else resolve(m.fields);
    },
    modalCancel() {
      if (!this.modal) return;
      const m = this.modal;
      const resolve = m._resolve;
      this.modal = null;
      this.restoreModalFocus(m._previousFocus);
      resolve(m.kind === 'confirm' ? false : null);
    },
    stepReachable(i) {
      if (i === 0) return true;
      if (i === 1) return !!this.currentJob;
      if (i === 2) return this.sourceTexts.length > 0;
      if (i === 3) return this.translated;
      if (i === 4) return this.canExport;
      return false;
    },
    stepBlockReason(i) {
      if (i === 1) return '请先在「任务」步骤选择一个任务';
      if (i === 2) return '请先完成「提取」';
      if (i === 3) return '请先完成「翻译」';
      if (i === 4) return '请完成审核并确认所有空译文后再导出';
      return '';
    },
    translationReadyForReview() {
      if (!this.operationSummary || this.operationSummary.status !== 'succeeded') return false;
      if (!Array.isArray(this.translateResults) || this.translateResults.length !== this.operationSummary.total) return false;
      return this.translateResults.every(item => item && item.status === 'succeeded');
    },
    goStep(i) {
      if (!this.stepReachable(i)) { this.toast(this.stepBlockReason(i), 'warn'); return; }
      this.step = i;
    },
    async api(url, opts = {}) {
      let r;
      try {
        r = await fetch(url, { headers: {'Content-Type': 'application/json'}, ...opts });
      } catch (error) {
        const wrapped = new Error('无法连接本地服务，请确认应用仍在运行');
        wrapped.code = 'local_service_unreachable';
        wrapped.cause = error;
        throw wrapped;
      }
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        const detail = typeof d.detail === 'string'
          ? d.detail
          : (d.detail && d.detail.message) || d.message || r.statusText;
        const error = new Error(detail || `请求失败（HTTP ${r.status}）`);
        error.code = d.error_code || (d.detail && d.detail.error_code) || `http_${r.status}`;
        error.status = r.status;
        throw error;
      }
      return r.json();
    },
    resetJobState() {
      if (this.abortController) this.abortController.abort();
      this.extractInfo = null;
      this.sourceItems = [];
      this.sourceTexts = [];
      this.sourceText = '';
      this.currentSourceRevision = null;
      this.currentTranslationRevision = null;
      this.manualTranslations = '';
      this.manualItems = [];
      this.manualPasteDirty = false;
      this.manualLoadedOnce = false;
      this.editingManualRow = null;
      this.manualError = '';
      this.translateResults = [];
      this.operationSummary = null;
      this.translateDiagnostics = [];
      this.translateSources = [];
      this.translateBlocks = [];
      this.translateBlocksList = [];
      this.translateThinking = {};
      this.translatePreviews = {};
      this.translateBlockSaved = new Set();
      this.translateDiagnosticSaved = new Set();
      this.translateProgress = 0;
      this.translateTotal = 0;
      this.translateDone = 0;
      this.translating = false;
      this.retryingFailed = false;
      clearInterval(this._translateTimer);
      this._translateTimer = null;
      this.abortController = null;
      this.currentOperationId = null;
      this.failedRows = [];
      this.reviewItems = [];
      this.reviewState = 'idle';
      this.reviewError = '';
      this.reviewSaveState = 'idle';
      this.reviewSaveError = '';
      this.reviewRevision = null;
      this.translated = false;
      this.translatedTxt = '';
      this.applyInfo = null;
      this.applyError = '';
      this.richTextPolicy = 'flatten';
      this.editingRow = null;
      this.selectedTermFilter = null;
      this.lastDiagnostic = null;
    },
    isCurrentJobRequest(job, token) {
      return this.currentJob === job && this.jobRequestToken === token;
    },
    async refreshJobs() {
      this.jobsState = 'loading';
      this.jobsError = '';
      try {
        this.jobs = await this.api('/api/jobs');
        this.jobsState = 'ready';
        this.loadGlossary();
      } catch (e) {
        this.jobsState = 'error';
        this.jobsError = e.message;
        this.toast('加载任务失败: ' + e.message, 'error');
      }
    },
    async loadGlossary() {
      this.glossaryState = 'loading';
      this.glossaryError = '';
      try {
        const g = await this.api('/api/glossary');
        this.glossaryDetail = g;
        this.glossaryCategories = Object.keys(g.categories || {});
        // 默认全部选中
        this.selectedCategories = [...this.glossaryCategories];
        this.glossaryState = 'ready';
      } catch (e) {
        this.glossaryState = 'error';
        this.glossaryError = e.message;
        this.toast('加载术语库失败: ' + e.message, 'error');
      }
    },
    async loadGlossaryDetail() {
      this.glossaryState = 'loading';
      this.glossaryError = '';
      try {
        this.glossaryDetail = await this.api('/api/glossary');
        if (!this.glossaryCategories.length) {
          this.glossaryCategories = Object.keys(this.glossaryDetail.categories || {});
        }
        this.glossaryState = 'ready';
      } catch (e) {
        this.glossaryState = 'error';
        this.glossaryError = e.message;
        this.toast('加载术语库失败: ' + e.message, 'error');
      }
    },
    async addTerm() {
      const t = this.newTerm;
      if (!t.source || !t.target) { this.toast('原文和译文必填'); return; }
      try {
        await this.api('/api/glossary/terms', {
          method: 'POST',
          body: JSON.stringify({category: t.category || '默认', source: t.source, target: t.target, note: t.note || ''}),
        });
        this.newTerm = {category: '', source: '', target: '', note: ''};
        this.showAddTerm = false;
        await this.loadGlossaryDetail();
        await this.loadGlossary();
        this.toast('术语已新增');
      } catch (e) { this.toast('新增失败: ' + e.message); }
    },
    async editTerm(category, entry) {
      const fields = await this.formModal({
        title: '编辑术语「' + entry.source + '」',
        fields: [
          { key: 'target', label: '译文', value: entry.target, placeholder: '译文' },
          { key: 'note', label: '备注', value: entry.note || '', placeholder: '可选' },
        ],
        okText: '保存',
      });
      if (!fields) return;
      const target = fields.find(f => f.key === 'target').value.trim();
      const note = fields.find(f => f.key === 'note').value;
      if (!target) { this.toast('译文不能为空', 'warn'); return; }
      try {
        await this.api('/api/glossary/terms', {
          method: 'PUT',
          body: JSON.stringify({category, source: entry.source, target, note}),
        });
        await this.loadGlossaryDetail();
        this.toast('已更新', 'success');
      } catch (e) { this.toast('更新失败: ' + e.message, 'error'); }
    },
    async deleteTerm(category, source) {
      if (!(await this.confirmModal({ title: '删除术语', message: '删除术语「' + source + '」？', danger: true, okText: '删除' }))) return;
      try {
        await this.api(`/api/glossary/terms?category=${encodeURIComponent(category)}&source=${encodeURIComponent(source)}`, {method: 'DELETE'});
        await this.loadGlossaryDetail();
        await this.loadGlossary();
        this.toast('已删除');
      } catch (e) { this.toast('删除失败: ' + e.message); }
    },
    async onFileSelected(e) {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      if (ext === 'xls') {
        this.toast('暂不支持 .xls，请在 Excel/WPS 中“另存为” .xlsx 后再选择。', 'error');
        e.target.value = '';
        return;
      }
      if (ext !== 'xlsx') {
        this.toast('仅支持 .xlsx 文件', 'error');
        e.target.value = '';
        return;
      }
      this.uploadingFile = true;
      try {
        // 浏览器原生文件选择器 → 上传到后端 → 返回服务器路径
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch('/api/upload', {method: 'POST', body: fd});
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          throw new Error(d.detail || r.statusText);
        }
        const res = await r.json();
        this.newJobInput = res.path;
        this.toast('文件已选择');
      } catch (err) { this.toast('上传失败: ' + err.message); }
      finally {
        this.uploadingFile = false;
        e.target.value = '';  // 允许重复选同一文件
      }
    },
    async loadSettings() {
      this.settingsState = 'loading';
      this.settingsError = '';
      try {
        this.settings = normalizeSettingsForUi(await this.api('/api/settings'));
        this.pendingApiKeys = {};
        this.mirrorsText = (this.settings.ai.mirrors || []).join('\n');
        this.activeProviderKey = this.settings.ai.active_provider || 'openai';
        this.engine = this.settings.ai.engine || 'google';
        const names = this.providerModelNames(this.activeProviderKey);
        if (names.length) {
          // 记住上次选的模型（存于 ai.active_model），否则用第一个
          const last = this.settings.ai.active_model;
          this.activeModel = (last && names.includes(last)) ? last : names[0];
          this.expandedModel = this.activeProviderKey + '/' + this.activeModel;
        }
        this.settingsState = 'ready';
      } catch (e) {
        this.settingsState = 'error';
        this.settingsError = e.message;
        this.toast('加载设置失败: ' + e.message, 'error');
      }
    },
    settingsPayload() {
      const payload = JSON.parse(JSON.stringify(this.settings));
      const providers = (payload.ai && payload.ai.providers) || {};
      Object.entries(providers).forEach(([key, provider]) => {
        delete provider.api_key_masked;
        delete provider.masked_api_key;
        delete provider.api_key_configured;
        delete provider.has_api_key;
        if (hasOwn(this.pendingApiKeys, key)) provider.api_key = this.pendingApiKeys[key];
        else delete provider.api_key;
      });
      return payload;
    },
    async saveSettings() {
      try {
        const response = await this.api('/api/settings', {
          method: 'PUT',
          body: JSON.stringify(this.settingsPayload()),
        });
        this.settings = normalizeSettingsForUi(response);
        this.settingsState = 'ready';
        this.settingsError = '';
        return true;
      } catch (e) {
        this.settingsState = 'error';
        this.settingsError = '保存失败：' + e.message;
        this.toast('保存设置失败: ' + e.message, 'error');
        return false;
      }
    },
    async updateProvider(key, field, value) {
      if (field === 'api_key') {
        await this.updateProviderKey(key, value);
        return;
      }
      const p = this.settings.ai.providers[key];
      if (!p) return;
      p[field] = value;
      await this.saveSettings();
    },
    providerKeyPlaceholder(key) {
      const provider = this.settings.ai.providers[key] || {};
      if (!provider.api_key_configured) return '尚未配置，输入 API Key';
      return provider.api_key_masked
        ? `已配置（${provider.api_key_masked}），输入新值可替换`
        : '已配置，输入新值可替换';
    },
    async updateProviderKey(key, value) {
      const provider = this.settings.ai.providers[key];
      if (!provider) return;
      this.pendingApiKeys[key] = value;
      const saved = await this.saveSettings();
      delete this.pendingApiKeys[key];
      if (!saved) {
        this.toast('密钥未保存且已从页面清除，请检查后重新输入', 'error');
      }
    },
    async testProvider(key) {
      const p = this.settings.ai.providers[key];
      if (!p) return;
      this.testingProvider = key;
      try {
        const res = await this.api('/api/providers/test', {
          method: 'POST',
          body: JSON.stringify({ provider_id: key }),
        });
        this.providerTestResults[key] = res;
        this.toast(res.ok ? '连接正常' : '连接失败', res.ok ? 'success' : 'error');
      } catch (e) {
        this.providerTestResults[key] = { ok: false, error: e.message };
        this.toast('测试失败: ' + e.message, 'error');
      } finally {
        this.testingProvider = '';
      }
    },
    // ---------- 模型行（摘要 + 展开） ----------
    providerModelNames(key) {
      const p = this.settings.ai.providers[key];
      if (!p) return [];
      p.model_configs = p.model_configs || {};
      return Object.keys(p.model_configs);
    },
    isExpanded(key, m) {
      return this.expandedModel === key + '/' + m;
    },
    toggleExpand(key, m) {
      this.expandedModel = this.expandedModel === key + '/' + m ? '' : key + '/' + m;
    },
    modelSummary(key, m) {
      const mc = this.modelConfigOf(key, m);
      const parts = [];
      if (mc.model_context) parts.push(Math.round(mc.model_context / 1000) + 'k');
      if (mc.temperature != null) parts.push('temp ' + mc.temperature);
      if (mc.max_tokens) parts.push('out ' + mc.max_tokens);
      if (mc.thinking && mc.thinking.type === 'enabled') parts.push('思考');
      if (mc.reasoning_effort) parts.push('effort ' + mc.reasoning_effort);
      if (mc.output_format) parts.push(mc.output_format === 'text' ? '文本' : mc.output_format.toUpperCase());
      if (mc.response_format === 'json_object') parts.push('json_obj');
      else if (mc.response_format === 'json_schema') parts.push('json_schema');
      return parts.length ? parts.join(' · ') : '（未配置，点击展开设置）';
    },
    async setActiveModelFor(key, m) {
      if (key !== this.activeProviderKey) {
        this.settings.ai.active_provider = key;
        this.activeProviderKey = key;
      }
      this.activeModel = m;
      this.settings.ai.active_model = m;
      await this.saveSettings();
    },
    async addModel(key) {
      const fields = await this.formModal({
        title: '新增模型',
        fields: [{ key: 'name', label: '模型名', value: '', placeholder: '如 deepseek-chat' }],
        okText: '添加',
      });
      if (!fields) return;
      const name = fields[0].value.trim();
      if (!name) return;
      const p = this.settings.ai.providers[key];
      p.model_configs = p.model_configs || {};
      const n = name.trim();
      if (p.model_configs[n]) { this.toast('模型已存在'); return; }
      p.model_configs[n] = {model_context: 128000, temperature: 0.6};
      this.unmarkRemoved(key, n);
      if (key === this.activeProviderKey) {
        this.settings.ai.active_model = n;
        this.activeModel = n;
      }
      this.expandedModel = key + '/' + n;
      await this.saveSettings();
    },
    async removeModel(key, m) {
      if (!(await this.confirmModal({ title: '删除模型', message: '删除模型「' + m + '」的配置？', danger: true, okText: '删除' }))) return;
      const p = this.settings.ai.providers[key];
      if (p.model_configs) delete p.model_configs[m];
      // 记录到 removed_models，防止 server 深合并把默认模型又加回来
      p.removed_models = p.removed_models || [];
      if (!p.removed_models.includes(m)) p.removed_models.push(m);
      if (key === this.activeProviderKey && this.activeModel === m) {
        const rest = Object.keys(p.model_configs || {});
        this.activeModel = rest.length ? rest[0] : '';
        this.settings.ai.active_model = this.activeModel;
      }
      if (this.expandedModel === key + '/' + m) this.expandedModel = '';
      await this.saveSettings();
      this.toast(`已删除模型「${m}」`);
    },
    unmarkRemoved(key, m) {
      // 重新添加时清除删除标记
      const p = this.settings.ai.providers[key];
      if (p && p.removed_models) p.removed_models = p.removed_models.filter(x => x !== m);
    },
    async setActiveProvider(key) {
      this.settings.ai.active_provider = key;
      this.activeProviderKey = key;
      const names = this.providerModelNames(key);
      if (names.length) {
        this.activeModel = names[0];
        this.settings.ai.active_model = names[0];
        this.expandedModel = key + '/' + names[0];
      } else {
        this.activeModel = '';
        this.settings.ai.active_model = '';
      }
      await this.saveSettings();
    },
    async changeModel(m) {
      // 切换模型时记住选择，供下次打开恢复
      this.activeModel = m;
      this.settings.ai.active_model = m;
      await this.saveSettings();
    },
    async addProvider() {
      const fields = await this.formModal({
        title: '新增供应商',
        fields: [{ key: 'name', label: '供应商名称', value: '', placeholder: '如 新供应商' }],
        okText: '添加',
      });
      if (!fields) return;
      const name = fields[0].value.trim() || '新供应商';
      const key = 'custom' + Date.now();
      this.settings.ai.providers[key] = {
        name, base_url: 'https://api.openai.com/v1',
        default_model: '',
        model_configs: {},
      };
      await this.saveSettings();
    },
    // ---------- 模型级配置 ----------
    modelConfigOf(key, m) {
      const p = this.settings.ai.providers[key];
      if (!p) return {};
      p.model_configs = p.model_configs || {};
      if (!p.model_configs[m]) p.model_configs[m] = {};
      return p.model_configs[m];
    },
    modelConfigValue(key, m, field, fallback) {
      const mc = this.modelConfigOf(key, m);
      const v = mc[field];
      if (v === undefined || v === null) return fallback;
      // thinking 存的是 {type: "enabled"/"disabled"}，下拉需要字符串值
      if (field === 'thinking' && typeof v === 'object') return v.type || fallback;
      return v;
    },
    modelConfigExtra(key, m) {
      const mc = this.modelConfigOf(key, m);
      return mc.extra ? JSON.stringify(mc.extra, null, 0) : '';
    },
    async updateModelConfig(key, m, field, value, kind) {
      const mc = this.modelConfigOf(key, m);
      if (kind === 'number') {
        const n = value === '' || value === null ? null : Number(value);
        if (n !== null && (isNaN(n) || n < 0)) { this.toast('无效数值'); return; }
        mc[field] = n;
      } else if (field === 'thinking') {
        mc[field] = value === '' ? undefined : {type: value};
      } else {
        mc[field] = value === '' ? undefined : value;
      }
      if (field === 'output_format' && value !== 'json' && ['json_object', 'json_schema'].includes(mc.response_format)) {
        mc.response_format = 'none';
      }
      await this.saveSettings();
    },
    async updateModelConfigExtra(key, m, text) {
      const mc = this.modelConfigOf(key, m);
      const t = text.trim();
      if (!t) { delete mc.extra; await this.saveSettings(); return; }
      try { mc.extra = JSON.parse(t); }
      catch (e) { this.toast('JSON 格式错误: ' + e.message); return; }
      await this.saveSettings();
    },
    // ---------- OpenRouter ----------
    async loadOpenRouter() {
      this.openrouterLoading = true;
      try {
        const res = await this.api('/api/openrouter/models');
        this.openrouterModels = res.models || [];
        if (!this.openrouterModels.length) this.toast('OpenRouter 返回空列表');
      } catch (e) { this.toast('拉取失败: ' + e.message); }
      finally { this.openrouterLoading = false; }
    },
    async applyOpenRouterModel(om) {
      // 把 OpenRouter 模型加入当前供应商（模型名取 id 去供应商前缀），填完整默认配置
      const key = this.activeProviderKey;
      const p = this.settings.ai.providers[key];
      if (!p) return;
      const modelName = om.id.includes('/') ? om.id.split('/').pop() : om.id;
      p.model_configs = p.model_configs || {};
      p.model_configs[modelName] = p.model_configs[modelName] || {};
      this.unmarkRemoved(key, modelName);
      this.fillModelFromOpenRouter(key, modelName, om);
      this.settings.ai.active_model = modelName;
      this.activeModel = modelName;
      this.expandedModel = key + '/' + modelName;
      await this.saveSettings();
      const parts = [];
      if (om.context_length) parts.push('上下文 ' + Math.round(om.context_length / 1000) + 'k');
      if (om.max_completion_tokens) parts.push('输出上限 ' + om.max_completion_tokens);
      if (om.supports_reasoning) parts.push('推理开启');
      this.toast(`已应用 ${om.id}：${parts.join('，') || '（无可用元数据）'}`);
    },
    // 用 OpenRouter 模型元数据填充完整默认配置：按模型真实能力填满，不保守
    fillModelFromOpenRouter(key, m, om) {
      const mc = this.modelConfigOf(key, m);
      // 上下文：模型真实能力
      if (om.context_length) mc.model_context = om.context_length;
      // 输出上限：OpenRouter 报告的 max_completion_tokens（若模型支持 max_tokens 请求参数）
      if (om.max_completion_tokens) {
        mc.max_tokens = om.max_completion_tokens;
      }
      // 默认温度（OpenRouter 报告的模型默认值）
      if (om.default_temperature != null) mc.temperature = om.default_temperature;
      // 推理：用 OpenRouter reasoning 元数据（supported_efforts / default_effort）
      if (om.supports_reasoning) {
        mc.thinking = {type: 'enabled'};
      }
      const r = om.reasoning;
      if (r && typeof r === 'object') {
        if (Array.isArray(r.supported_efforts) && r.supported_efforts.length) {
          // 存支持级别（UI 下拉用，下划线前缀不传给 API）
          mc._effort_options = r.supported_efforts;
        }
        if (r.default_effort) {
          mc.reasoning_effort = r.default_effort;
        }
      }
      return mc;
    },
    // 当前模型支持哪些 effort 级别（下拉选项）
    modelEffortOptions(key, m) {
      const mc = this.modelConfigOf(key, m);
      return (mc._effort_options && mc._effort_options.length)
        ? mc._effort_options
        : ['low', 'medium', 'high', 'max'];
    },
    async applyOpenRouterToModel(key, m) {
      // 单个模型：按名称匹配 OpenRouter 模型，填完整默认配置
      // 若还没拉取过模型列表，先自动拉取
      if (!this.openrouterModels.length) {
        this.toast('正在拉取 OpenRouter 模型列表…');
        await this.loadOpenRouter();
        if (!this.openrouterModels.length) { this.toast('拉取失败，无法填充'); return; }
      }
      let found = this.openrouterModels.find(x => x.id.endsWith('/' + m) || x.id === m);
      if (!found) {
        this.toast(`OpenRouter 中未找到「${m}」`);
        return;
      }
      this.fillModelFromOpenRouter(key, m, found);
      await this.saveSettings();
      const parts = [];
      if (found.context_length) parts.push('上下文 ' + Math.round(found.context_length / 1000) + 'k');
      if (found.max_completion_tokens) parts.push('输出上限 ' + found.max_completion_tokens);
      if (found.supports_reasoning) parts.push('推理开启');
      this.toast(`已用 OpenRouter 配置填充 ${m}：${parts.join('，')}`);
    },
    async removeProvider(key) {
      if (Object.keys(this.settings.ai.providers).length <= 1) {
        this.toast('至少保留一个供应商');
        return;
      }
      if (!(await this.confirmModal({ title: '删除供应商', message: '删除供应商「' + this.settings.ai.providers[key].name + '」？', danger: true, okText: '删除' }))) return;
      delete this.settings.ai.providers[key];
      if (this.activeProviderKey === key) {
        this.activeProviderKey = Object.keys(this.settings.ai.providers)[0];
        this.settings.ai.active_provider = this.activeProviderKey;
        const names = this.providerModelNames(this.activeProviderKey);
        this.activeModel = names[0] || '';
        this.settings.ai.active_model = this.activeModel;
      }
      await this.saveSettings();
    },
    onEngineChange() {
      this.settings.ai.engine = this.engine;
      this.saveSettings();
    },
    onProviderChange() {
      const names = this.providerModelNames(this.activeProviderKey);
      if (names.length) {
        const last = this.settings.ai.active_model;
        this.activeModel = (last && names.includes(last)) ? last : names[0];
      }
    },
    async deleteCategory(name) {
      const count = this.glossaryDetail.categories[name] ? this.glossaryDetail.categories[name].length : 0;
      if (!(await this.confirmModal({ title: '删除类别', message: '删除整个类别「' + name + '」及其 ' + count + ' 个术语？', danger: true, okText: '删除' }))) return;
      try {
        await this.api(`/api/glossary/categories?category=${encodeURIComponent(name)}`, {method: 'DELETE'});
        await this.loadGlossaryDetail();
        await this.loadGlossary();
        this.toast('类别已删除');
      } catch (e) { this.toast('删除失败: ' + e.message); }
    },
    async loadMirrors() {
      this.mirrorsState = 'loading';
      this.mirrorsError = '';
      try {
        const r = await this.api('/api/mirrors');
        this.mirrorsText = r.mirrors.join('\n');
        this.mirrorsState = 'ready';
      } catch (e) {
        this.mirrorsState = 'error';
        this.mirrorsError = e.message;
        this.toast('加载镜像站失败: ' + e.message, 'error');
      }
    },
    async saveMirrors() {
      const lines = this.mirrorsText.split('\n').map(s => s.trim()).filter(Boolean);
      if (!lines.length) { this.toast('镜像站列表不能为空'); return; }
      this.settings.ai.mirrors = lines;
      this.customMirrors = lines;
      await this.saveSettings();
      this.toast('镜像站已保存');
    },
    async testMirrors() {
      this.testingMirrors = true;
      this.mirrorTestResults = [];
      const mirrors = this.mirrorsText.split('\n').map(s => s.trim()).filter(Boolean);
      if (!mirrors.length) { this.testingMirrors = false; this.toast('请先填写镜像站'); return; }
      try {
        const r = await this.api('/api/mirrors/test', {method: 'POST', body: JSON.stringify({mirrors})});
        this.mirrorTestResults = r.results;
        this.toast('镜像站测试完成');
      } catch (e) { this.toast('测试失败: ' + e.message); }
      finally { this.testingMirrors = false; }
    },
    async createJob() {
      const ext = (this.newJobInput.split('.').pop() || '').toLowerCase();
      if (ext === 'xls') {
        this.toast('暂不支持 .xls，请在 Excel/WPS 中“另存为” .xlsx 后再创建任务。', 'error');
        return;
      }
      if (ext !== 'xlsx') {
        this.toast('仅支持 .xlsx 文件', 'error');
        return;
      }
      try {
        await this.api('/api/jobs', {
          method: 'POST',
          body: JSON.stringify({job: this.newJobName || null, input: this.newJobInput, sep: '\\n'}),
        });
        this.newJobInput = ''; this.newJobName = '';
        await this.refreshJobs();
        this.toast('任务已创建');
      } catch (e) { this.toast('创建失败: ' + e.message); }
    },
    async selectJob(j) {
      const token = ++this.jobRequestToken;
      this.resetJobState();
      this.currentJob = j.job;
      if (j.needs_reextract) {
        this.step = 1;
        this.toast('该任务来自旧版本，请重新提取后继续', 'warn');
        return;
      }
      if (j.stage_code === 'exported') this.step = 4;
      else if (j.stage_code === 'translated') this.step = 3;
      else if (j.stage_code === 'extracted' || j.stage_code === 'translation_partial') this.step = 2;
      else this.step = 1;

      if (j.output_translated || j.output_bilingual) {
        this.applyInfo = {
          translated_output: j.output_translated || null,
          bilingual_output: j.output_bilingual || null,
        };
      }

      try {
        if (j.source_revision) {
          await this.loadSourcePreview(j.job, token);
          if (!this.isCurrentJobRequest(j.job, token)) return;
          await this.restoreAiOutput(j.job, token);
        }
        if (!this.isCurrentJobRequest(j.job, token)) return;
        this.toast('已选择任务: ' + j.job);
      } catch (e) {
        if (this.isCurrentJobRequest(j.job, token)) {
          this.toast('恢复任务失败: ' + e.message, 'error');
        }
      }
    },
    async restoreAiOutput(job = this.currentJob, token = this.jobRequestToken) {
      const d = await this.api(`/api/jobs/${job}/ai_output`);
      if (!this.isCurrentJobRequest(job, token)) return;
      this.currentSourceRevision = d.source_revision || this.currentSourceRevision;
      this.currentTranslationRevision = d.translation_revision || null;
      this.translateResults = d.results || [];
      this.operationSummary = d.summary || null;
      this.translateDiagnostics = d.diagnostics || [];
      this.translateBlocks = d.blocks || [];
      this.translateBlocksList = (d.blocks || []).map(b => b.base);
      this.translateSources = this.sourceTexts;
      this.translateTotal = this.sourceTexts.length;
      this.translatedTxt = this.translateResults.map(r => r.translation).join('\n');
      this.reviewItems = this.buildReviewItems(this.translateResults);
      this.reviewState = 'ready';
      await this.loadReview(job, token);
      this.failedRows = this.translateResults
        .filter(item => item.status !== 'succeeded')
        .map(item => item.id);
      if (this.operationSummary) {
        this.operationSummary = this.validateSummary(this.operationSummary, this.translateTotal);
        this.translateDone = this.operationSummary.succeeded + this.operationSummary.failed + this.operationSummary.cancelled;
        this.translateProgress = this.translateTotal ? Math.floor(this.translateDone / this.translateTotal * 100) : 100;
      }
      this.translated = this.translationReadyForReview();
      if (this.translated && this.step === 2) {
        this.step = this.reviewReady ? 4 : 3;
      }
    },
    // Review contract (the backend worker must implement these exact shapes):
    // GET  /api/jobs/{job}/review?source_revision=...&translation_revision=...
    //   -> {source_revision, translation_revision, review_revision, items: []}
    // PUT  /api/jobs/{job}/review
    //   body {source_revision, translation_revision, decisions: [{review_id,
    //   kind, decision, target, category, apply_to_text,
    //   empty_translation_confirmed, row_ids, selected_row_ids}]}
    //   -> the same response shape.  IDs are opaque stable strings owned by
    //   the backend; the deterministic fallback below is only for the first
    //   render before GET returns, never for an export authorization decision.
    reviewFallbackId(kind, term, rows) {
      return kind + ':' + encodeURIComponent(term || '') + ':' + [...(rows || [])].sort((a, b) => a - b).join(',');
    },
    buildReviewItems(results, existing = []) {
      const previous = new Map((existing || []).map(item => [item.review_id, item]));
      const items = this.collectTerms(results).map(item => {
        const reviewId = item.review_id || this.reviewFallbackId('term', item.term, item.rows);
        const old = previous.get(reviewId);
        return {
          ...item,
          review_id: reviewId,
          kind: 'term',
          decision: old ? old.decision : 'pending',
          target: old && typeof old.target === 'string' ? old.target : (item.target || ''),
          category: old && old.category ? old.category : item.category,
          applyToText: old && old.applyToText !== undefined ? old.applyToText : true,
          selectedRows: old && Array.isArray(old.selectedRows)
            ? [...old.selectedRows]
            : [...(item.rows || [])],
          empty_translation_confirmed: false,
        };
      });
      for (const result of results || []) {
        if (result.status !== 'succeeded' || typeof result.translation !== 'string' || result.translation.trim()) continue;
        const rows = [result.id];
        const reviewId = this.reviewFallbackId('blank_translation', '', rows);
        const old = previous.get(reviewId);
        items.push({
          review_id: reviewId,
          kind: 'blank_translation',
          term: '', reason: '该行译文为空', candidate: '', target: '', rows,
          row_ids: rows,
          decision: old ? old.decision : 'pending',
          applyToText: false,
          selectedRows: [],
          empty_translation_confirmed: Boolean(old && old.empty_translation_confirmed),
        });
      }
      return items.sort((a, b) => (a.rows[0] || 0) - (b.rows[0] || 0) || a.review_id.localeCompare(b.review_id));
    },
    normalizeReviewItems(items, fallback = []) {
      if (!Array.isArray(items)) throw new Error('审核响应 items 必须是数组');
      const seen = new Set();
      return items.map((raw) => {
        if (!raw || typeof raw !== 'object' || typeof raw.review_id !== 'string' || !raw.review_id) {
          throw new Error('审核响应包含缺少 review_id 的条目');
        }
        if (seen.has(raw.review_id)) throw new Error('审核响应包含重复 review_id');
        seen.add(raw.review_id);
        const rows = Array.isArray(raw.row_ids) ? raw.row_ids : (Array.isArray(raw.rows) ? raw.rows : []);
        if (rows.some(id => !Number.isInteger(id) || id < 0)) throw new Error('审核响应 row_ids 非法');
        const selectedRows = Array.isArray(raw.selected_row_ids)
          ? raw.selected_row_ids
          : (Boolean(raw.apply_to_text ?? raw.applyToText) ? rows : []);
        if (selectedRows.some(id => !Number.isInteger(id) || !rows.includes(id))) {
          throw new Error('审核响应 selected_row_ids 非法');
        }
        const kind = raw.kind === 'blank_translation' ? 'blank_translation' : 'term';
        const decision = raw.decision || 'pending';
        if (!['pending', 'accepted', 'edited', 'ignored'].includes(decision)) throw new Error('审核响应 decision 非法');
        return {
          ...raw,
          review_id: raw.review_id,
          kind,
          rows,
          row_ids: rows,
          decision,
          target: typeof raw.target === 'string' ? raw.target : '',
          category: typeof raw.category === 'string' && raw.category
            ? raw.category
            : (this.glossaryCategories[0] || '默认'),
          applyToText: selectedRows.length > 0,
          selectedRows: [...selectedRows],
          empty_translation_confirmed: Boolean(raw.empty_translation_confirmed),
        };
      });
    },
    reviewSemanticKey(item) {
      return [item.kind || 'term', item.term || '', ...(item.rows || [])].join('|');
    },
    mergeReviewItems(serverItems) {
      const fallback = this.buildReviewItems(this.translateResults, this.reviewItems);
      const serverByKey = new Map(serverItems.map(item => [this.reviewSemanticKey(item), item]));
      const merged = fallback.map(item => serverByKey.get(this.reviewSemanticKey(item)) || item);
      const known = new Set(merged.map(item => item.review_id));
      for (const item of serverItems) {
        if (!known.has(item.review_id)) merged.push(item);
      }
      return merged.sort((a, b) => (a.rows[0] || 0) - (b.rows[0] || 0) || a.review_id.localeCompare(b.review_id));
    },
    async loadReview(job = this.currentJob, token = this.jobRequestToken) {
      if (!job || !this.currentSourceRevision) return false;
      this.reviewState = 'loading';
      this.reviewError = '';
      try {
        const query = new URLSearchParams({source_revision: this.currentSourceRevision});
        if (this.currentTranslationRevision) query.set('translation_revision', this.currentTranslationRevision);
        const data = await this.api(`/api/jobs/${encodeURIComponent(job)}/review?${query}`);
        if (!this.isCurrentJobRequest(job, token)) return false;
        if (data.source_revision !== this.currentSourceRevision) throw new Error('审核记录与当前原文版本不一致');
        if (this.currentTranslationRevision && data.translation_revision !== this.currentTranslationRevision) {
          throw new Error('审核记录与当前译文版本不一致');
        }
        const serverItems = this.normalizeReviewItems(data.items || []);
        this.reviewItems = this.mergeReviewItems(serverItems);
        this.reviewRevision = data.review_revision || null;
        this.reviewState = 'ready';
        this.reviewSaveState = 'ready';
        this.reviewSaveError = '';
        this.translated = this.translationReadyForReview();
        return true;
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.reviewState = 'error';
          this.reviewError = e.message || '审核记录加载失败';
          this.recordDiagnostic('review_load', e);
        }
        return false;
      }
    },
    reviewPayload() {
      return {
        source_revision: this.currentSourceRevision,
        translation_revision: this.currentTranslationRevision,
        decisions: this.reviewItems.map(item => ({
          review_id: item.review_id,
          kind: item.kind,
          decision: item.decision,
          target: item.target || '',
          category: item.category || null,
          apply_to_text: Boolean(item.applyToText),
          empty_translation_confirmed: Boolean(item.empty_translation_confirmed),
          row_ids: [...(item.rows || [])],
          selected_row_ids: item.applyToText ? [...(item.selectedRows || [])] : [],
        })),
      };
    },
    async saveReview(job = this.currentJob, token = this.jobRequestToken) {
      if (!job || !this.currentSourceRevision) throw new Error('缺少当前任务或原文版本');
      this.reviewSaveState = 'saving';
      this.reviewSaveError = '';
      try {
        const data = await this.api(`/api/jobs/${encodeURIComponent(job)}/review`, {
          method: 'PUT',
          body: JSON.stringify(this.reviewPayload()),
        });
        if (!this.isCurrentJobRequest(job, token)) return false;
        if (data.source_revision !== this.currentSourceRevision) throw new Error('保存后的审核版本已变化，请刷新任务');
        // A successful review transaction rewrites the translation artifact
        // and therefore legitimately advances translation_revision.  The
        // server already checked the revision supplied in the request; keep
        // the returned revision for the next decision/export instead of
        // mistaking that expected advancement for a conflict.
        if (typeof data.translation_revision === 'string') {
          this.currentTranslationRevision = data.translation_revision;
        }
        this.reviewItems = this.mergeReviewItems(this.normalizeReviewItems(data.items || this.reviewItems));
        this.reviewRevision = data.review_revision || this.reviewRevision;
        this.reviewState = 'ready';
        this.reviewSaveState = 'ready';
        this.reviewSaveError = '';
        this.translated = this.translationReadyForReview();
        return true;
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.reviewSaveState = 'error';
          this.reviewSaveError = e.message || '审核保存失败';
          this.recordDiagnostic('review_save', e);
        }
        throw e;
      }
    },
    async reloadCurrentJob() {
      const job = this.currentJob;
      const token = ++this.jobRequestToken;
      if (!job) return;
      if (this.abortController) this.abortController.abort();
      this.translating = false;
      this._stopTimer();
      this.abortController = null;
      try {
        await this.loadSourcePreview(job, token);
        if (!this.isCurrentJobRequest(job, token)) return;
        await this.restoreAiOutput(job, token);
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.reviewState = 'error';
          this.reviewError = e.message || '任务恢复失败';
          this.recordDiagnostic('job_restore', e);
        }
      }
    },
    async doExtract() {
      if (this.sourceTexts.length || this.translated) {
        if (!(await this.confirmModal({ title: '重新提取', message: '该任务已提取或翻译过，重新提取会重建位置映射，可能使已有译文失效。确定继续？', danger: true, okText: '重新提取' }))) return;
      }
      this.extracting = true;
      const job = this.currentJob;
      const token = this.jobRequestToken;
      try {
        const result = await this.api(`/api/jobs/${job}/extract`, {method: 'POST'});
        if (!this.isCurrentJobRequest(job, token)) return;
        ++this.jobRequestToken;
        this.resetJobState();
        this.currentJob = job;
        this.extractInfo = result;
        this.currentSourceRevision = result.source_revision;
        this.sourceItems = result.items || [];
        this.sourceTexts = this.sourceItems.map(item => item.text);
        this.sourceText = this.sourceTexts.join('\n');
        this.toast(`提取完成，${this.extractInfo.unique_texts} 条文本`, 'success');
        this.step = 2;
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.toast('提取失败: ' + e.message, 'error');
        }
      }
      finally { this.extracting = false; }
    },
    async loadSourcePreview(job = this.currentJob, token = this.jobRequestToken) {
      const src = await this.api(`/api/jobs/${job}/source`);
      if (!this.isCurrentJobRequest(job, token)) return;
      this.currentSourceRevision = src.source_revision;
      this.sourceItems = src.items || [];
      this.sourceTexts = this.sourceItems.map(item => item.text);
      this.sourceText = this.sourceTexts.join('\n');
    },
    async copySource() {
      try {
        await navigator.clipboard.writeText(this.sourceText);
        this.toast('原文已复制');
      } catch (e) {
        // 降级：用临时 textarea 复制
        const ta = document.createElement('textarea');
        ta.value = this.sourceText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        this.toast('原文已复制');
      }
    },
    async switchToManual() {
      // 切到手动模式：若当前没有译文（或没加载过），自动加载已有译文作为起点
      const hadLoaded = this.manualLoadedOnce;
      this.translateMode = 'manual';
      if (!hadLoaded) {
        this.manualLoadedOnce = true;
        await this.loadManualStart();
      }
    },
    // 加载当前 revision 的结构化译文作为手动编辑起点
    async loadManualStart() {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      this.manualError = '';
      try {
        const d = await this.api(`/api/jobs/${job}/ai_output`);
        if (!this.isCurrentJobRequest(job, token)) return;
        if (d.results && d.results.length) {
          this.manualItems = d.results.map(r => ({id: r.id, translation: r.translation}));
          this.manualTranslations = '';
          this.manualPasteDirty = false;
          this.toast('已加载 AI 译文，可逐条修改', 'success');
        } else {
          this.manualItems = [];
          this.manualTranslations = '';
          this.manualPasteDirty = false;
          this.toast('尚无译文，粘贴外部 AI 翻译结果', 'warn');
        }
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.manualError = '读取手动译文失败：' + e.message;
          this.recordDiagnostic('manual_translation_load', e);
          this.toast(this.manualError, 'error');
        }
      }
    },
    async confirmLoadManual() {
      if (this.manualItems.length && !(await this.confirmModal({ title: '载入上次译文', message: '会用已保存的译文覆盖当前编辑内容，继续？', danger: true, okText: '覆盖' }))) return;
      await this.loadManualStart();
    },
    startManualEdit(i) {
      this.editingManualRow = i;
      this.$nextTick(() => {
        const els = Array.isArray(this.$refs.manualEditor) ? this.$refs.manualEditor : [this.$refs.manualEditor];
        els.forEach(e => { if (e) { e.style.height = 'auto'; e.style.height = e.scrollHeight + 'px'; } });
        setTimeout(() => { els.forEach(e => { if (e) e.focus(); }); }, 0);
      });
    },
    updateManualPaste(ev) {
      if (!this.manualBatchSafe) return;
      this.manualTranslations = ev.target.value;
      this.manualPasteDirty = true;
      this.manualError = '';
      this.translated = false;
      this.applyInfo = null;
      const lines = this.manualTranslations === ''
        ? []
        : this.manualTranslations.split('\n');
      this.manualItems = lines.map((translation, id) => ({id, translation}));
    },
    saveManualRow(i, ev) {
      const translation = ev.target.value;
      this.manualError = '';
      this.translated = false;
      this.applyInfo = null;
      const existing = this.manualItems.find(item => item.id === i);
      if (existing) existing.translation = translation;
      else this.manualItems.push({id: i, translation});
      this.manualItems.sort((a, b) => a.id - b.id);
      if (translation.includes('\n') || translation.includes('\r')) {
        this.manualTranslations = '';
        this.manualPasteDirty = false;
      } else if (this.manualPasteDirty) {
        const lines = this.manualTranslations === '' ? [] : this.manualTranslations.split('\n');
        lines[i] = translation;
        this.manualTranslations = lines.join('\n');
      }
      this.editingManualRow = null;
    },
    async saveManualTranslations() {
      // 批量粘贴只接受每条一行；内部状态始终保存为结构化 items
      this.manualError = '';
      if (this.manualLineStatus.diff !== 0) {
        this.manualError = `译文 ${this.manualLineStatus.count} 行 / 原文 ${this.manualLineStatus.expected} 行，请核对后再保存`;
        this.toast('⚠ ' + this.manualError, 'warn');
        return;
      }
      const emptyRows = this.manualEmptyRows;
      let emptyConfirmed = false;
      if (emptyRows.length) {
        const labels = emptyRows.slice(0, 8).map(row => '#' + (row.id + 1)).join('、');
        const suffix = emptyRows.length > 8 ? ' 等' : '';
        if (!(await this.confirmModal({
          title: '确认空译文',
          message: `第 ${labels}${suffix} 行译文为空。确认保留为空并继续保存？空译文未确认前不能导出。`,
          danger: true,
          okText: '确认并保存',
        }))) return;
        emptyConfirmed = true;
      }
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const sourceRevision = this.currentSourceRevision;
      const sourceTexts = [...this.sourceTexts];
      const manualItems = this.manualItems.map(item => ({...item}));
      try {
        // 构造与 AI 结果同构的 results（保留原不确定术语/思考）
        const prev = await this.api(`/api/jobs/${job}/ai_output`);
        if (!this.isCurrentJobRequest(job, token)) return;
        const prevResults = (prev.results || []);
        const results = sourceTexts.map((src, i) => {
          const prevOne = prevResults.find(r => r.id === i) || {};
          const manual = manualItems.find(item => item.id === i);
          return {
            id: i,
            translation: manual ? manual.translation : '',
            uncertain_terms: prevOne.uncertain_terms || [],
            status: 'succeeded',
            error: null,
            empty_translation_confirmed: emptyConfirmed && !(manual && manual.translation),
          };
        });
        const summary = this.buildSummaryFromResults(results, sourceTexts.length);
        const saved = await this.api(`/api/jobs/${job}/ai_output`, {
          method: 'POST',
          body: JSON.stringify({
            source_revision: sourceRevision,
            results,
            summary,
            blocks: prev.blocks || [],
            diagnostics: prev.diagnostics || [],
          }),
        });
        if (!this.isCurrentJobRequest(job, token)) return;
        this.translateResults = results;
        this.operationSummary = summary;
        this.translateDiagnostics = prev.diagnostics || [];
        this.translateSources = this.sourceTexts;
        this.currentTranslationRevision = saved.translation_revision;
        this.translatedTxt = results.map(item => item.translation).join('\n');
        this.failedRows = [];
        // The server owns the canonical review_id.  Reload it before sending
        // the confirmation decision; the local fallback ID is intentionally
        // never accepted as an export authorization token.
        await this.loadReview(job, token);
        if (emptyConfirmed) {
          this.reviewItems = this.reviewItems.map(item => item.kind === 'blank_translation'
            ? {...item, decision: 'accepted', empty_translation_confirmed: true}
            : item);
        }
        this.reviewState = 'ready';
        await this.saveReview(job, token);
        this.translated = this.translationReadyForReview();
        this.toast('译文已保存');
        this.step = this.canExport ? 4 : 3;
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.manualError = '保存失败：' + e.message;
          this.recordDiagnostic('manual_translation_save', e);
          this.toast(this.manualError, 'error');
        }
      }
    },
    async deleteJob(j) {
      if (!(await this.confirmModal({ title: '删除任务', message: '删除任务「' + j.job + '」及其所有文件？', danger: true, okText: '删除' }))) return;
      try {
        await this.api(`/api/jobs/${j.job}`, {method: 'DELETE'});
        this.jobs = this.jobs.filter(x => x.job !== j.job);
        if (this.currentJob === j.job) {
          ++this.jobRequestToken;
          this.resetJobState();
          this.currentJob = null;
          this.step = 0;
        }
        this.toast('任务已删除');
      } catch (e) { this.toast('删除失败: ' + e.message); }
    },
    async doTranslate() {
      if (this.translating) return;
      const operationJob = this.currentJob;
      const operationToken = this.jobRequestToken;
      this.translateError = '';
      this.translating = true; this.translateProgress = 0; this.translateResults = [];
      this.currentOperationId = null;
      this.translated = false;
      this.operationSummary = null;
      this.translateDiagnostics = [];
      this.translateTotal = 0; this.translateDone = 0;
      this.translateThinking = {};  // 块 base → 思考增量（翻译中实时显示）
      this.translatePreviews = {};  // id → 流式已解析片段（仅预览）
      this.translateAutoScroll = true;
      this.thinkingAutoScroll = true;
      this.translateBlocks = [];    // 已完成的思考块
      this.translateBlockSaved = new Set();
      this.translateDiagnosticSaved = new Set();
      this.selectedTermFilter = null;
      this.editingRow = null;
      this.failedRows = [];
      this.translateStartTime = Date.now();
      this.translateElapsed = 0;
      clearInterval(this._translateTimer);
      this._translateTimer = setInterval(() => { this.translateElapsed = Math.floor((Date.now() - this.translateStartTime) / 1000); }, 1000);
      let texts;
      try {
        texts = await this.loadSourceTexts();
      } catch (e) {
        if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
        this.translating = false;
        this._stopTimer();
        this.toast('读取原文失败: ' + e.message, 'error');
        return;
      }
      if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
      if (!texts.length) { this.translating = false; this._stopTimer(); this.toast('没有可翻译文本', 'warn'); return; }
      const operationSourceRevision = this.currentSourceRevision;
      this.translateSources = texts;
      this.abortController = new AbortController();
      let streamValidated = false;
      try {
        const provider = this.settings.ai.providers[this.activeProviderKey] || {};
        // 所选模型的独立配置（上下文/温度/输出上限/thinking 等）
        const model_config = (provider.model_configs && provider.model_configs[this.activeModel]) || {};
        const body = {
          texts,
          source: this.settings.ai.source_lang || 'en',
          target: this.settings.ai.target_lang || 'zh-CN',
          engine: this.engine,
          glossary_categories: this.selectedCategories,
          concurrency: this.settings.ai.concurrency || 4,
          mirrors: this.customMirrors || this.settings.ai.mirrors || null,
          provider_config: this.engine === 'openai'
            ? {provider_id: this.activeProviderKey, model: this.activeModel}
            : undefined,
          model_config,
          model_context: model_config.model_context || provider.model_context || this.settings.ai.model_context || null,
        };
        // 流式：SSE 解析
        const resp = await fetch('/api/translate/stream', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body),
          signal: this.abortController.signal,
        });
        if (!resp.ok) {
          const d = await resp.json().catch(() => ({}));
          throw new Error(d.detail || resp.statusText);
        }
        if (!resp.body || typeof resp.body.getReader !== 'function') {
          throw new Error('本地服务未返回可读取的翻译流');
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          buf += decoder.decode(value, {stream: true});
          // 按标准 SSE 空行切分，兼容 LF 与 CRLF；畸形事件不能静默丢弃。
          let separator;
          while ((separator = buf.match(/\r?\n\r?\n/)) !== null) {
            const idx = separator.index;
            const event = buf.slice(0, idx);
            buf = buf.slice(idx + separator[0].length);
            const data = this.parseSseEvent(event);
            if (this.isCurrentJobRequest(operationJob, operationToken)) {
              this.handleStreamEvent(data);
            }
          }
        }
        buf += decoder.decode();
        if (buf.trim()) {
          throw new Error('翻译流结束时仍有未完成事件，结果不能视为完整');
        }
        if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
        this._stopTimer();
        if (!this.operationSummary) {
          throw new Error('翻译流在最终 summary 前中断');
        }
        this.assertResultsMatchSummary(this.operationSummary, this.translateResults);
        streamValidated = true;
        const finalResults = [...this.translateResults].sort((a, b) => a.id - b.id);
        this.translateResults = finalResults;
        // 思考已全部 append 到 translateBlocks，清空实时增量
        this.translateThinking = {};
        this.translatePreviews = {};
        this.editingRow = null;
        this.reviewItems = this.buildReviewItems(finalResults);
        this.reviewState = 'ready';
        this.translatedTxt = finalResults.map(r => r.translation).join('\n');
        const saved = await this.persistAiOutput(operationJob, operationSourceRevision);
        if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
        this.currentTranslationRevision = saved.translation_revision || this.currentTranslationRevision;
        await this.loadReview(operationJob, operationToken);
        this.translated = this.translationReadyForReview();
        const summary = this.operationSummary;
        if (this.translated) {
          this.toast('翻译完成：' + summary.succeeded + '/' + summary.total + ' 条，' + this.pendingTerms.length + ' 个不确定术语', 'success');
          if (!this.reviewReady) this.step = 3;
          else this.step = 4;
        } else {
          this.toast('翻译未完成：成功 ' + summary.succeeded + '，失败 ' + summary.failed + '，取消 ' + summary.cancelled + '。请重试失败条目后再导出。', 'warn');
          this.step = 2;
        }
      } catch (e) {
        if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
        this.recordDiagnostic('translation_stream', e);
        this._stopTimer();
        if (streamValidated) {
          this.translateError = '结果已收到，但保存到本地失败：' + e.message;
          this.translated = false;
          this.step = 2;
          this.toast('翻译结果已完整接收，但本地保存失败: ' + e.message + '。修复后请重试，当前结果不能导出。', 'error');
          return;
        }
        if (this.translateTotal > 0) {
          this.translateError = e.message || '翻译流中断，未完成条目已标记';
          const cancelled = e.name === 'AbortError';
          this.completeInterruptedOperation(cancelled, e.message || '翻译流中断');
          try {
            await this.persistAiOutput(operationJob, operationSourceRevision);
          } catch (persistError) {
            if (this.isCurrentJobRequest(operationJob, operationToken)) {
              this.toast('保存未完成结果失败: ' + persistError.message, 'error');
            }
          }
          if (!this.isCurrentJobRequest(operationJob, operationToken)) return;
          this.translated = false;
          this.step = 2;
          if (cancelled) {
            this.toast('已停止：完成 ' + this.operationSummary.succeeded + '/' + this.operationSummary.total + ' 条，未完成结果不可导出', 'warn');
          } else {
            this.toast('翻译失败: ' + e.message + '。未完成结果已标记，不能导出。', 'error');
          }
        } else if (e.name === 'AbortError') {
          this.translateError = '翻译已停止';
          this.toast('翻译已停止', 'warn');
        } else {
          this.translateError = e.message || '翻译请求失败';
          this.toast('翻译失败: ' + e.message, 'error');
        }
      } finally {
        if (this.isCurrentJobRequest(operationJob, operationToken)) {
          this.translating = false;
          this.translatePreviews = {};
          this.abortController = null;
          this.currentOperationId = null;
        }
      }
    },
    async stopTranslate() {
      const operationId = this.currentOperationId;
      if (operationId) {
        try {
          await this.api(`/api/operations/${encodeURIComponent(operationId)}/cancel`, {
            method: 'POST',
          });
        } catch (e) {
          this.recordDiagnostic('translation_cancel', e);
          this.toast('停止信号未被本地服务确认；正在关闭页面连接。已发出的模型请求仍可能产生费用。', 'warn');
        }
      }
      if (this.abortController) this.abortController.abort();
    },
    parseSseEvent(event) {
      const dataLines = [];
      for (const line of String(event || '').split(/\r?\n/)) {
        if (!line || line.startsWith(':')) continue;
        if (!line.startsWith('data:')) {
          const error = new Error('翻译流包含未知 SSE 字段：' + line.split(':', 1)[0]);
          error.code = 'invalid_sse_field';
          throw error;
        }
        dataLines.push(line.slice(5).replace(/^ /, ''));
      }
      if (!dataLines.length) {
        const error = new Error('翻译流包含没有 data 的畸形事件');
        error.code = 'invalid_sse_event';
        throw error;
      }
      try {
        return JSON.parse(dataLines.join('\n'));
      } catch (cause) {
        const error = new Error('翻译流事件不是合法 JSON');
        error.code = 'invalid_sse_json';
        error.cause = cause;
        throw error;
      }
    },
    async retryFailed() {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const sourceRevision = this.currentSourceRevision;
      const ids = [...this.failedRows];
      if (!ids.length || this.retryingFailed) return;
      const texts = ids.map(id => this.translateSources[id]).filter(t => t !== undefined);
      if (!texts.length) { this.toast('没有可重试的失败行', 'warn'); return; }
      this.retryingFailed = true;
      this.translateError = '';
      try {
        const provider = this.settings.ai.providers[this.activeProviderKey] || {};
        const model_config = (provider.model_configs && provider.model_configs[this.activeModel]) || {};
        const body = {
          texts,
          source: this.settings.ai.source_lang || 'en',
          target: this.settings.ai.target_lang || 'zh-CN',
          engine: this.engine,
          glossary_categories: this.selectedCategories,
          concurrency: this.settings.ai.concurrency || 4,
          mirrors: this.customMirrors || this.settings.ai.mirrors || null,
          provider_config: this.engine === 'openai'
            ? {provider_id: this.activeProviderKey, model: this.activeModel}
            : undefined,
          model_config,
        };
        const res = await this.api('/api/translate', { method: 'POST', body: JSON.stringify(body) });
        if (!this.isCurrentJobRequest(job, token)) return;
        const retrySummary = this.validateSummary(res.summary, texts.length);
        this.assertResultsMatchSummary(retrySummary, res.results || []);
        let ok = 0, fail = 0;
        (res.results || []).forEach((r) => {
          const gid = ids[r.id];
          if (!Number.isInteger(gid)) throw new Error('重试结果 ID 无法映射到原文');
          const mapped = {...r, id: gid};
          const index = this.translateResults.findIndex(x => x.id === gid);
          if (index >= 0) this.translateResults.splice(index, 1, mapped);
          else this.translateResults.push(mapped);
          if (r.status === 'succeeded') ok++;
          else fail++;
        });
        this.translateResults.sort((a, b) => a.id - b.id);
        this.operationSummary = this.buildSummaryFromResults(this.translateResults, this.translateTotal);
        this.failedRows = this.translateResults.filter(item => item.status !== 'succeeded').map(item => item.id);
        this.translatedTxt = this.translateResults.map(x => x.translation).join('\n');
        this.reviewItems = this.buildReviewItems(this.translateResults.filter(item => item.status === 'succeeded'), this.reviewItems);
        const saved = await this.persistAiOutput(job, sourceRevision);
        if (!this.isCurrentJobRequest(job, token)) return;
        this.currentTranslationRevision = saved.translation_revision || this.currentTranslationRevision;
        await this.loadReview(job, token);
        this.translated = this.translationReadyForReview();
        this.toast('重试完成：成功 ' + ok + ' 行' + (fail ? '，仍失败 ' + fail + ' 行' : ''), fail ? 'warn' : 'success');
        if (this.translated) this.step = this.reviewReady ? 4 : 3;
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.translateError = e.message || '重试失败';
          this.recordDiagnostic('translation_retry', e);
          this.toast('重试失败: ' + e.message, 'error');
        }
      } finally {
        if (this.isCurrentJobRequest(job, token)) this.retryingFailed = false;
      }
    },
    _stopTimer() {
      clearInterval(this._translateTimer);
      this._translateTimer = null;
    },
    // 保存 AI 输出（逐行译文/不确定术语/思考）到任务目录
    async persistAiOutput(
      job = this.currentJob,
      sourceRevision = this.currentSourceRevision,
    ) {
      try {
        if (!this.operationSummary) throw new Error('缺少翻译 summary，拒绝保存为可导出结果');
        this.assertResultsMatchSummary(this.operationSummary, this.translateResults);
        const saved = await this.api(`/api/jobs/${job}/ai_output`, {
          method: 'POST',
          body: JSON.stringify({
            source_revision: sourceRevision,
            results: this.translateResults,
            summary: this.operationSummary,
            blocks: this.translateBlocks,
            diagnostics: this.translateDiagnostics,
          }),
        });
        if (job === this.currentJob && sourceRevision === this.currentSourceRevision) {
          this.currentTranslationRevision = saved.translation_revision;
        }
        return saved;
      } catch (e) {
        if (job === this.currentJob && sourceRevision === this.currentSourceRevision) {
          this.toast('保存 AI 输出失败: ' + e.message, 'error');
        }
        throw e;
      }
    },
    startEdit(id) {
      this.editingRow = id;
      this.$nextTick(() => {
        const els = Array.isArray(this.$refs.rowEditor) ? this.$refs.rowEditor : [this.$refs.rowEditor];
        els.forEach(e => { if (e) { e.style.height = 'auto'; e.style.height = e.scrollHeight + 'px'; } });
      });
      // 延迟聚焦，避免 textarea 刚挂载的 blur 立即触发保存
      this.focusRowEditor();
    },
    autosizeRow(ev) {
      ev.target.style.height = 'auto';
      ev.target.style.height = ev.target.scrollHeight + 'px';
    },
    saveEdit(id, ev) {
      this.updateTranslation(id, ev.target.value);
      this.editingRow = null;
    },
    // textarea 挂载后立即 focus 会误触 blur，延迟到下一个宏任务再聚焦
    focusRowEditor() {
      this.$nextTick(() => {
        setTimeout(() => {
          const els = Array.isArray(this.$refs.rowEditor) ? this.$refs.rowEditor : [this.$refs.rowEditor];
          els.forEach(e => { if (e) e.focus(); });
        }, 0);
      });
    },
    updateTranslation(id, value) {
      const r = this.translateResults.find(x => x.id === id);
      if (r) r.translation = value;
      this.reviewItems = this.buildReviewItems(this.translateResults, this.reviewItems);
      // 同步导出文本（与旧逻辑保持一致：译文按行拼接）
      this.translatedTxt = this.translateResults.map(x => x.translation).join('\n');
    },
    toggleTermFilter(term) {
      this.selectedTermFilter = this.selectedTermFilter === term ? null : term;
    },
    validateSummary(raw, expectedTotal = this.translateTotal) {
      const names = ['status', 'total', 'succeeded', 'failed', 'cancelled', 'succeeded_ids', 'failed_ids', 'cancelled_ids'];
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('summary 必须是对象');
      const actualNames = Object.keys(raw).filter(name => name !== 'type').sort();
      const expectedNames = [...names].sort();
      if (actualNames.length !== expectedNames.length || actualNames.some((name, index) => name !== expectedNames[index])) {
        throw new Error('summary 包含缺失或未知字段');
      }
      if ('type' in raw && raw.type !== 'summary') throw new Error('summary 事件类型非法');
      for (const name of names) {
        if (!(name in raw)) throw new Error('summary 缺少字段 ' + name);
      }
      const summary = {};
      names.forEach(name => { summary[name] = raw[name]; });
      for (const name of ['total', 'succeeded', 'failed', 'cancelled']) {
        if (!Number.isInteger(summary[name]) || summary[name] < 0) throw new Error('summary.' + name + ' 非法');
      }
      if (summary.total !== expectedTotal) throw new Error('summary.total 与输入数量不一致');
      if (summary.total !== summary.succeeded + summary.failed + summary.cancelled) {
        throw new Error('summary 计数不守恒');
      }
      const groups = [
        ['succeeded_ids', 'succeeded'],
        ['failed_ids', 'failed'],
        ['cancelled_ids', 'cancelled'],
      ];
      const all = [];
      for (const [idsName, countName] of groups) {
        const ids = summary[idsName];
        if (!Array.isArray(ids) || ids.length !== summary[countName]) throw new Error('summary.' + idsName + ' 计数不一致');
        if (ids.some(id => !Number.isInteger(id) || id < 0 || id >= summary.total)) throw new Error('summary.' + idsName + ' 包含非法 ID');
        if (ids.some((id, index) => index > 0 && ids[index - 1] >= id)) throw new Error('summary.' + idsName + ' 必须严格递增且不重复');
        all.push(...ids);
      }
      const sorted = [...all].sort((a, b) => a - b);
      if (sorted.length !== summary.total || sorted.some((id, index) => id !== index)) throw new Error('summary ID 集合未完整覆盖输入');
      let status = 'partial';
      if (summary.succeeded === summary.total) status = 'succeeded';
      else if (summary.failed === summary.total) status = 'failed';
      else if (summary.cancelled === summary.total) status = 'cancelled';
      if (summary.status !== status) throw new Error('summary.status 与计数不一致');
      return summary;
    },
    buildSummaryFromResults(results, total = this.translateTotal) {
      const byId = new Map();
      for (const item of results || []) {
        if (!Number.isInteger(item.id) || item.id < 0 || item.id >= total || byId.has(item.id)) throw new Error('翻译结果 ID 集合非法');
        byId.set(item.id, item);
      }
      const succeeded_ids = [], failed_ids = [], cancelled_ids = [];
      for (let id = 0; id < total; id++) {
        const item = byId.get(id);
        const status = item ? item.status : 'cancelled';
        if (status === 'succeeded') succeeded_ids.push(id);
        else if (status === 'failed') failed_ids.push(id);
        else if (status === 'cancelled') cancelled_ids.push(id);
        else throw new Error('翻译结果状态非法: ' + status);
      }
      let status = 'partial';
      if (succeeded_ids.length === total) status = 'succeeded';
      else if (failed_ids.length === total) status = 'failed';
      else if (cancelled_ids.length === total) status = 'cancelled';
      return this.validateSummary({
        status,
        total,
        succeeded: succeeded_ids.length,
        failed: failed_ids.length,
        cancelled: cancelled_ids.length,
        succeeded_ids,
        failed_ids,
        cancelled_ids,
      }, total);
    },
    assertResultsMatchSummary(summary, results) {
      const valid = this.validateSummary(summary, summary.total);
      if (!Array.isArray(results) || results.length !== valid.total) throw new Error('结果条数与 summary 不一致');
      const byId = new Map();
      for (const item of results) {
        if (!item || !Number.isInteger(item.id) || byId.has(item.id) || typeof item.translation !== 'string') throw new Error('翻译结果结构或 ID 非法');
        byId.set(item.id, item);
      }
      const expectedStatus = new Map();
      valid.succeeded_ids.forEach(id => expectedStatus.set(id, 'succeeded'));
      valid.failed_ids.forEach(id => expectedStatus.set(id, 'failed'));
      valid.cancelled_ids.forEach(id => expectedStatus.set(id, 'cancelled'));
      for (let id = 0; id < valid.total; id++) {
        const item = byId.get(id);
        if (!item || item.status !== expectedStatus.get(id)) throw new Error('结果状态与 summary 不一致: ID ' + id);
      }
      return true;
    },
    completeInterruptedOperation(cancelled, message) {
      const byId = new Map(this.translateResults.map(item => [item.id, item]));
      for (let id = 0; id < this.translateTotal; id++) {
        const existing = byId.get(id);
        if (existing && ['succeeded', 'failed', 'cancelled'].includes(existing.status)) continue;
        const status = cancelled ? 'cancelled' : 'failed';
        byId.set(id, {
          id,
          translation: this.translateSources[id] || '',
          uncertain_terms: [],
          status,
          error: message,
          error_code: cancelled ? 'cancelled' : 'stream_incomplete',
        });
      }
      this.translateResults = [...byId.values()].sort((a, b) => a.id - b.id);
      this.operationSummary = this.buildSummaryFromResults(this.translateResults, this.translateTotal);
      this.failedRows = this.translateResults.filter(item => item.status !== 'succeeded').map(item => item.id);
      this.translateDone = this.operationSummary.succeeded + this.operationSummary.failed + this.operationSummary.cancelled;
      this.translateProgress = this.translateTotal ? Math.floor(this.translateDone / this.translateTotal * 100) : 100;
      this.translatedTxt = this.translateResults.map(item => item.translation).join('\n');
    },
    // ---------- 粘滞滚动：接近底部时自动跟随，用户上滚后解除 ----------
    _scrollNearBottom(el) {
      if (!el) return false;
      return el.scrollHeight - el.scrollTop - el.clientHeight < 64;
    },
    onTranslateListScroll(ev) {
      this.translateAutoScroll = this._scrollNearBottom(ev.target);
    },
    onThinkingScroll(ev) {
      this.thinkingAutoScroll = this._scrollNearBottom(ev.target);
    },
    _scrollToBottom(refName, stickyFlag) {
      if (!this[stickyFlag]) return;
      this.$nextTick(() => {
        if (!this[stickyFlag]) return;
        const el = this.$refs[refName];
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
    scrollTranslateListToBottom() {
      this._scrollToBottom('translateMapList', 'translateAutoScroll');
    },
    scrollThinkingToBottom() {
      this._scrollToBottom('thinkingScroll', 'thinkingAutoScroll');
    },
    _refreshPreviewProgress() {
      const shown = Object.keys(this.translatePreviews).length;
      this.translateDone = Math.max(this.translateDone, shown);
      this.translateProgress = this.translateTotal ? Math.floor(this.translateDone / this.translateTotal * 100) : 100;
    },
    handleStreamEvent(data) {
      if (data.type === 'meta') {
        if (!Number.isInteger(data.total) || data.total < 0) throw new Error('meta.total 非法');
        if (typeof data.operation_id !== 'string' || !data.operation_id) throw new Error('meta.operation_id 非法');
        this.currentOperationId = data.operation_id;
        this.translateTotal = data.total;
        this.translateChunks = data.chunks;
        this.translateBlocksList = data.blocks || [];
      } else if (data.type === 'thinking') {
        const id = data.id;
        this.translateThinking[id] = (this.translateThinking[id] || '') + (data.delta || '');
        this.scrollThinkingToBottom();
      } else if (data.type === 'item_preview') {
        const id = data.id;
        if (!Number.isInteger(id) || id < 0 || id >= this.translateTotal) throw new Error('预览事件 ID 非法');
        if (typeof data.translation !== 'string') throw new Error('预览事件 translation 非法');
        this.translatePreviews[id] = {
          translation: data.translation,
          uncertain_terms: Array.isArray(data.uncertain_terms) ? data.uncertain_terms : [],
        };
        this._refreshPreviewProgress();
        this.scrollTranslateListToBottom();
      } else if (data.type === 'progress') {
        if (!Number.isInteger(data.completed) || data.completed < 0 || data.completed > this.translateTotal) throw new Error('progress.completed 非法');
        this.translateDone = Math.max(data.completed, Object.keys(this.translatePreviews).length);
        this.translateProgress = this.translateTotal ? Math.floor(this.translateDone / this.translateTotal * 100) : 100;
      } else if (data.type === 'item_succeeded' || data.type === 'item_failed' || data.type === 'item_cancelled') {
        const id = data.id;
        if (!Number.isInteger(id) || id < 0 || id >= this.translateTotal) throw new Error('结果事件 ID 非法');
        if (data.block_id !== undefined && data.thinking && !this.translateBlockSaved.has(data.block_id)) {
          this.translateBlockSaved.add(data.block_id);
          this.translateBlocks.push({base: data.block_id, text: data.thinking});
          delete this.translateThinking[data.block_id];
        }
        delete this.translatePreviews[id];
        if (data.diagnostic !== undefined && !this.translateDiagnosticSaved.has(data.block_id)) {
          this.translateDiagnosticSaved.add(data.block_id);
          this.translateDiagnostics.push({
            block_id: data.block_id,
            status: data.type === 'item_succeeded' ? 'succeeded' : (data.type === 'item_cancelled' ? 'cancelled' : 'failed'),
            error_code: data.error_code || null,
            error: data.error || null,
            provider_response: data.diagnostic,
          });
        }
        const status = data.type === 'item_succeeded' ? 'succeeded' : (data.type === 'item_cancelled' ? 'cancelled' : 'failed');
        if (typeof data.translation !== 'string' || !Array.isArray(data.uncertain_terms)) throw new Error('结果事件 payload 非法');
        const existing = this.translateResults.find(r => r.id === id);
        if (existing) {
          existing.translation = data.translation;
          existing.uncertain_terms = data.uncertain_terms || [];
          existing.status = status;
          existing.error = data.error || null;
          existing.error_code = data.error_code || null;
          if (data.thinking) existing.thinking = data.thinking;
        } else {
          this.translateResults.push({
            id, translation: data.translation, uncertain_terms: data.uncertain_terms || [],
            thinking: data.thinking, status, error: data.error || null,
            error_code: data.error_code || null,
          });
        }
        if (status !== 'succeeded' && !this.failedRows.includes(id)) this.failedRows.push(id);
        this.scrollTranslateListToBottom();
      } else if (data.type === 'summary') {
        if (this.operationSummary) throw new Error('翻译流返回了重复 summary');
        this.operationSummary = this.validateSummary(data, this.translateTotal);
      } else {
        throw new Error('未知 SSE 事件类型: ' + data.type);
      }
    },
    async loadSourceTexts() {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const src = await this.api(`/api/jobs/${job}/source`);
      if (!this.isCurrentJobRequest(job, token)) return [];
      this.currentSourceRevision = src.source_revision;
      this.sourceItems = src.items || [];
      this.sourceTexts = this.sourceItems.map(item => item.text);
      this.sourceText = this.sourceTexts.join('\n');
      return this.sourceTexts;
    },
    collectTerms(results) {
      const map = {};
      for (const r of results) {
        for (const t of r.uncertain_terms || []) {
          if (!t.term) continue;
          if (!map[t.term]) {
            map[t.term] = {
              ...t,
              target: t.candidate || '',
              category: this.glossaryCategories[0] || '默认',
              rows: [],
              row_ids: [],
              applyToText: true,
              selectedRows: [],
            };
          }
          if (!map[t.term].rows.includes(r.id)) {
            map[t.term].rows.push(r.id);
            map[t.term].selectedRows.push(r.id);
          }
        }
      }
      return Object.values(map)
        .map(item => ({...item, row_ids: [...item.rows]}))
        .sort((a, b) => a.rows[0] - b.rows[0]);
    },
    async acceptReview(item) {
      if (!item || item.decision !== 'pending') return;
      if (item.kind === 'blank_translation') {
        if (!(await this.confirmModal({
          title: '确认空译文',
          message: `第 ${(item.rows[0] || 0) + 1} 行译文为空。确认保留为空？`,
          danger: true,
          okText: '确认空译文',
        }))) return;
        await this.setReviewDecision(item.review_id, 'accepted', {empty_translation_confirmed: true});
        return;
      }
      await this.acceptTerm(item);
    },
    async setReviewDecision(reviewId, decision, patch = {}) {
      const index = this.reviewItems.findIndex(item => item.review_id === reviewId);
      if (index < 0) throw new Error('找不到审核条目：' + reviewId);
      if (!['pending', 'accepted', 'edited', 'ignored'].includes(decision)) throw new Error('审核决定非法');
      const next = {...this.reviewItems[index], ...patch, decision};
      this.reviewItems.splice(index, 1, next);
      try {
        await this.saveReview(this.currentJob, this.jobRequestToken);
      } catch (e) {
        // 保留本地改动以便用户重试，但不让导出门控误认为已成功持久化。
        this.reviewSaveError = e.message || '审核保存失败';
        throw e;
      }
    },
    async acceptTerm(t) {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const sourceRevision = this.currentSourceRevision;
      const category = t.category === '__new' ? (t.newCategory || '默认') : t.category;
      try {
        await this.api('/api/glossary/terms', {
          method: 'POST',
          body: JSON.stringify({category, source: t.term, target: t.target || t.term, note: t.reason || ''}),
        });
        if (!this.isCurrentJobRequest(job, token)) return;
        let hit = -1; // -1 = 未启用应用到译文
        if (t.applyToText) hit = await this.applyTermToRows(t, job, sourceRevision);
        if (!this.isCurrentJobRequest(job, token)) return;
        const decision = (t.target || '').trim() !== (t.candidate || '').trim() ? 'edited' : 'accepted';
        await this.setReviewDecision(t.review_id, decision, {
          target: t.target || t.term,
          category,
          applyToText: Boolean(t.applyToText && (t.selectedRows || []).length),
          selectedRows: [...(t.selectedRows || [])],
        });
        await this.loadGlossary();
        if (!this.isCurrentJobRequest(job, token)) return;
        if (hit === 0) this.toast('已入库，但未在译文中找到候选译法，请回到翻译区手动核对', 'warn');
        else if (hit > 0) this.toast('已入库，已替换 ' + hit + ' 行', 'success');
        else this.toast('已入库', 'success');
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.toast('入库失败: ' + e.message, 'error');
        }
      }
    },
    async applyTermToRows(t, job = this.currentJob, sourceRevision = this.currentSourceRevision) {
      let hit = 0;
      for (const id of (t.selectedRows || [])) {
        const r = this.translateResults.find(x => x.id === id);
        if (!r) continue;
        const before = r.translation;
        // Replacement is deliberately limited to the exact result IDs the
        // model attached to this review item.  Never rewrite all rows or the
        // original source text as a side effect of accepting one term.
        if (t.target && t.candidate && t.candidate !== t.target) {
          r.translation = r.translation.split(t.candidate).join(t.target);
        }
        if (t.target && t.term && t.term !== t.target) {
          r.translation = r.translation.split(t.term).join(t.target);
        }
        if (r.translation !== before) hit++;
      }
      if (hit) {
        this.translatedTxt = this.translateResults.map(x => x.translation).join('\n');
        await this.persistAiOutput(job, sourceRevision);
      }
      return hit;
    },
    replacementPreview(t, id) {
      let translated = this.rowTranslation(id);
      if (!translated) return '';
      if (t.target && t.candidate && t.candidate !== t.target) {
        translated = translated.split(t.candidate).join(t.target);
      }
      if (t.target && t.term && t.term !== t.target) {
        translated = translated.split(t.term).join(t.target);
      }
      return translated;
    },
    reviewRowSelected(t, id) {
      return Boolean(t.applyToText && Array.isArray(t.selectedRows) && t.selectedRows.includes(id));
    },
    setReviewRowSelected(t, id, selected) {
      const current = new Set(Array.isArray(t.selectedRows) ? t.selectedRows : []);
      if (selected) current.add(id);
      else current.delete(id);
      t.selectedRows = [...current]
        .filter(rowId => (t.rows || []).includes(rowId))
        .sort((a, b) => a - b);
      t.applyToText = t.selectedRows.length > 0;
    },
    selectAllReviewRows(t) {
      t.selectedRows = [...(t.rows || [])];
      t.applyToText = t.selectedRows.length > 0;
    },
    clearReviewRows(t) {
      t.selectedRows = [];
      t.applyToText = false;
    },
    rowSource(id) {
      return this.translateSources[id] || '';
    },
    rowTranslation(id) {
      const r = this.translateResults.find(x => x.id === id);
      return r ? r.translation : '';
    },
    async ignoreReview(reviewId) {
      try {
        await this.setReviewDecision(reviewId, 'ignored');
        this.toast('已忽略此审核项', 'success');
      } catch (e) {
        this.toast('忽略失败：' + e.message, 'error');
      }
    },
    ignoreTerm(i) {
      const item = this.pendingTerms[i];
      if (item) return this.ignoreReview(item.review_id);
    },
    async acceptAll() {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      if (!(await this.confirmModal({ title: '全部接受', message: '将接受 ' + this.pendingReviews.length + ' 个待审核项（包括空译文确认），继续？', okText: '全部接受' }))) return;
      for (const item of [...this.pendingReviews]) {
        if (!this.isCurrentJobRequest(job, token)) return;
        if (item.kind === 'blank_translation') {
          await this.setReviewDecision(item.review_id, 'accepted', {empty_translation_confirmed: true});
        } else {
          await this.acceptTerm(item);
        }
      }
    },
    async skipAll() {
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const skippable = [...this.pendingTerms];
      if (!skippable.length) return;
      if (!(await this.confirmModal({ title: '全部忽略术语', message: '将忽略 ' + skippable.length + ' 个术语审核项。空译文仍必须确认，继续？', danger: true, okText: '全部忽略' }))) return;
      if (!this.isCurrentJobRequest(job, token)) return;
      try {
        for (const item of skippable) {
          const index = this.reviewItems.findIndex(candidate => candidate.review_id === item.review_id);
          if (index >= 0) this.reviewItems.splice(index, 1, {...item, decision: 'ignored'});
        }
        await this.saveReview(job, token);
      } catch (e) {
        this.toast('保存忽略决定失败：' + e.message, 'error');
      }
    },
    async chooseRichTextPolicy(retry = false) {
      const selected = await this.richTextPolicyModal();
      if (!selected) return;
      this.richTextPolicy = selected;
      if (retry) await this.doApply();
    },
    async doApply() {
      if (!this.canExport) {
        this.toast('翻译 summary 尚未完整成功，不能导出', 'warn');
        return;
      }
      const allowedPolicies = new Set(['preserve_original', 'flatten']);
      const richTextPolicy = allowedPolicies.has(this.richTextPolicy)
        ? this.richTextPolicy
        : 'flatten';
      this.richTextPolicy = richTextPolicy;
      const job = this.currentJob;
      const token = this.jobRequestToken;
      const sourceRevision = this.currentSourceRevision;
      this.applyError = '';
      this.applying = true;
      try {
        const saved = await this.persistAiOutput(job, sourceRevision);
        if (!this.isCurrentJobRequest(job, token)) return;
        const translationRevision = saved.translation_revision;
        this.currentTranslationRevision = translationRevision;
        await this.saveReview(job, token);
        if (!this.isCurrentJobRequest(job, token)) return;
        const exportTranslationRevision = this.currentTranslationRevision;
        if (!exportTranslationRevision) throw new Error('审核保存后缺少当前译文版本');
        const applyInfo = await this.api(`/api/jobs/${job}/apply`, {
          method: 'POST',
          body: JSON.stringify({
            source_revision: sourceRevision,
            translation_revision: exportTranslationRevision,
            rich_text_policy: richTextPolicy,
          }),
        });
        if (!this.isCurrentJobRequest(job, token)) return;
        this.applyInfo = applyInfo;
        await this.refreshJobs();  // 刷新任务列表，让任务区出现下载按钮
        if (!this.isCurrentJobRequest(job, token)) return;
        this.toast('导出完成，可下载文件');
      } catch (e) {
        if (this.isCurrentJobRequest(job, token)) {
          this.applyError = '导出失败：' + e.message;
          this.recordDiagnostic('export', e);
          this.toast(this.applyError, 'error');
        }
      } finally {
        if (this.isCurrentJobRequest(job, token)) this.applying = false;
      }
    },
  },
  mounted() {
    this.refreshJobs();
    this.loadSettings();
    this.loadMirrors();
    this._onDocumentKeydown = (e) => {
      if (!this.modal) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        this.modalCancel();
        return;
      }
      if (e.key === 'Tab') {
        const root = this.$refs.modalBox;
        if (!root) return;
        const focusable = [...root.querySelectorAll('button, input, textarea, select, a[href]')]
          .filter(el => !el.disabled && el.getAttribute('aria-hidden') !== 'true');
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
        return;
      }
      if (e.key === 'Enter' && this.modal.kind === 'confirm' && !['TEXTAREA', 'BUTTON'].includes(e.target.tagName)) {
        e.preventDefault();
        this.modalOk();
      }
    };
    document.addEventListener('keydown', this._onDocumentKeydown);
  },
}).mount('#app');
