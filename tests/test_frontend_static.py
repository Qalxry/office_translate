"""Focused frontend source and runtime-unit checks.

These checks intentionally do not claim to be browser E2E coverage.  They
verify the repository-native HTML/CSS contract and execute the Vue options
object in Node for state-machine invariants that do not require a DOM.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).parents[1]
WEB = ROOT / "office_translate" / "gui" / "web"


class _ElementCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs):
        self.elements.append((tag, dict(attrs)))


def _elements():
    parser = _ElementCollector()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return parser.elements


def test_keyboard_controls_dialog_and_live_regions_are_semantic():
    elements = _elements()
    click_targets = [(tag, attrs) for tag, attrs in elements if "@click" in attrs]
    interactive = {"button", "a", "input", "select", "textarea", "summary"}
    offenders = [
        (tag, attrs.get("class"))
        for tag, attrs in click_targets
        if tag not in interactive
        and attrs.get("role") != "button"
        and "modal-overlay" not in (attrs.get("class") or "")
    ]
    assert not offenders, f"non-keyboard click targets: {offenders}"

    assert any(
        tag == "div"
        and attrs.get("role") == "dialog"
        and attrs.get("aria-modal") == "true"
        and attrs.get(":aria-labelledby")
        for tag, attrs in elements
    )
    assert any(attrs.get("aria-live") == "polite" for _, attrs in elements)
    assert any(attrs.get("role") == "alert" for _, attrs in elements)
    assert any(
        tag == "button" and "step" in (attrs.get("class") or "").split()
        for tag, attrs in elements
    )


def test_desktop_layout_and_focus_selectors_are_explicit():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "@media (min-width: 900px) and (max-width: 1040px)" in css
    assert "@media (min-width: 900px) and (max-height: 760px)" in css
    assert ".translate-workspace" in css and "min-height:280px" in css
    assert ".recovery-card" in css
    assert ".caret" not in css
    assert "@keyframes blink" not in css


def test_review_contract_uses_one_structured_state_and_stable_keys():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert "pendingTerms: []" not in app
    assert "reviewItems: []" in app
    assert "/review?${query}" in app
    assert "method: 'PUT'" in app
    assert "source_revision: this.currentSourceRevision" in app
    assert "translation_revision: this.currentTranslationRevision" in app
    assert "empty_translation_confirmed" in app
    assert "selected_row_ids" in app
    assert "replacementPreview" in app
    assert "reviewRowSelected" in app
    assert "逐行差异" in index
    assert "选择要修改的行" in index
    assert ':key="t.review_id"' in index
    assert ':key="m.id"' in index
    assert "this.operationSummary.status === 'succeeded'" in app
    assert "this.reviewReady" in app
    assert "this.unconfirmedBlankTranslations.length === 0" in app
    assert "/api/operations/${encodeURIComponent(operationId)}/cancel" in app
    reset_start = app.index("resetJobState()")
    reset_end = app.index("isCurrentJobRequest", reset_start)
    reset_body = app[reset_start:reset_end]
    assert "this.reviewItems = []" in reset_body
    assert "this.reviewState = 'idle'" in reset_body
    assert "this.lastDiagnostic = null" in reset_body


def test_json_response_format_defaults_to_stream_compatible_none():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert "modelConfigValue(key, m, 'response_format', 'none')" in index
    assert "无（默认，流式兼容性最好）" in index
    assert "json_object/json_schema 可能被供应商整包返回" in index
    assert "mc.response_format = 'none'" in app


def test_rich_text_export_policy_is_explicit_and_style_claim_is_bounded():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert "richTextPolicy: 'flatten'" in app
    assert "richTextPolicy: 'block'" not in app
    assert "rich_text_policy: richTextPolicy" in app
    assert "kind: 'rich-text-policy'" in app
    assert "阻止并取消导出（block，默认）" not in index
    assert "保留原文（preserve_original）" in index
    assert "转为纯文本（flatten，默认）" in index
    assert "受影响的源单元格保持原文" in index
    assert "纯文本译文替换整个富文本单元格" in index
    assert "modal.kind === 'rich-text-policy'" in index
    assert "样式完全保留" not in index


def test_rich_text_policy_is_passed_to_apply_api_under_node():
    app_path = (WEB / "app.js").as_posix()
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        global.document = {{
          activeElement: null,
          contains: () => false,
          addEventListener: () => {{}},
        }};
        global.navigator = {{clipboard: {{writeText: async () => {{}}}}}};
        global.Vue = {{createApp(options) {{
          global.__options = options;
          return {{mount() {{ return options; }}}};
        }}}};
        vm.runInThisContext(fs.readFileSync({app_path!r}, 'utf8'), {{filename: 'app.js'}});

        (async () => {{
          const options = global.__options;
          const state = options.data();
          Object.assign(state, options.methods);
          if (state.richTextPolicy !== 'flatten') throw new Error('export did not default to flatten');

          state.currentJob = 'job';
          state.jobRequestToken = 7;
          state.currentSourceRevision = 'src';
          state.canExport = true;
          state.isCurrentJobRequest = () => true;
          state.persistAiOutput = async () => ({{translation_revision: 'tr'}});
          state.saveReview = async () => {{}};
          state.refreshJobs = async () => {{}};
          state.toast = () => {{}};
          const policies = [];
          state.api = async (url, opts) => {{
            if (url.endsWith('/apply')) policies.push(JSON.parse(opts.body).rich_text_policy);
            return {{translated_output: 'translated.xlsx', bilingual_output: 'bilingual.xlsx'}};
          }};

          await state.doApply();
          state.richTextPolicy = 'preserve_original';
          await state.doApply();
          state.richTextPolicy = 'flatten';
          await state.doApply();
          if (JSON.stringify(policies) !== JSON.stringify(['flatten', 'preserve_original', 'flatten'])) {{
            throw new Error('unexpected apply policies: ' + JSON.stringify(policies));
          }}
        }})().catch((error) => {{
          console.error(error);
          process.exitCode = 1;
        }});
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_review_and_sse_state_machine_runs_under_node():
    app_path = (WEB / "app.js").as_posix()
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        global.document = {{
          activeElement: null,
          contains: () => false,
          addEventListener: () => {{}},
        }};
        global.navigator = {{clipboard: {{writeText: async () => {{}}}}}};
        global.Vue = {{createApp(options) {{
          global.__options = options;
          return {{mount() {{ return options; }}}};
        }}}};
        vm.runInThisContext(fs.readFileSync({app_path!r}, 'utf8'), {{filename: 'app.js'}});
        const options = global.__options;
        if (!options) throw new Error('Vue options were not captured');
        const state = options.data();
        const methods = options.methods;
        const computed = options.computed;
        Object.assign(state, methods);

        state.translateSources = ['source'];
        const built = state.buildReviewItems([{{
          id: 0, translation: '', status: 'succeeded', uncertain_terms: []
        }}]);
        if (built.length !== 1 || built[0].kind !== 'blank_translation') throw new Error('blank review missing');
        if (built[0].review_id !== state.buildReviewItems([{{
          id: 0, translation: '', status: 'succeeded', uncertain_terms: []
        }}])[0].review_id) throw new Error('fallback review id is unstable');

        state.reviewItems = built;
        state.reviewState = 'ready';
        Object.defineProperty(state, 'pendingReviews', {{get: () => computed.pendingReviews.call(state)}});
        Object.defineProperty(state, 'unconfirmedBlankTranslations', {{get: () => computed.unconfirmedBlankTranslations.call(state)}});
        if (computed.reviewReady.call(state)) throw new Error('unconfirmed blank became review-ready');
        state.operationSummary = {{status: 'succeeded', total: 1}};
        state.translateResults = [{{id: 0, translation: '译文', status: 'succeeded'}}];
        if (!state.translationReadyForReview()) throw new Error('pending review blocked access to review step');

        const parsed = state.parseSseEvent('data: {{"type":"meta","total":1,"operation_id":"op-1"}}\\r\\n');
        if (parsed.type !== 'meta' || parsed.total !== 1) throw new Error('valid CRLF SSE rejected');
        let rejected = false;
        try {{ state.parseSseEvent('event: message\\ndata: {{}}'); }} catch (error) {{
          rejected = error.code === 'invalid_sse_field';
        }}
        if (!rejected) throw new Error('unknown SSE field was accepted');

        state.currentJob = 'job';
        state.currentSourceRevision = 'src';
        state.currentTranslationRevision = 'tr';
        state.reviewItems = [{{
          review_id: 'review-1', kind: 'term', decision: 'edited', target: '译文',
          category: '默认', applyToText: true, rows: [0], selectedRows: [0], empty_translation_confirmed: false,
        }}];
        const payload = state.reviewPayload();
        if (payload.decisions[0].review_id !== 'review-1') throw new Error('review id lost');
        if (payload.decisions[0].decision !== 'edited') throw new Error('decision lost');
        if (payload.decisions[0].row_ids[0] !== 0) throw new Error('row scope lost');
        if (payload.decisions[0].selected_row_ids[0] !== 0) throw new Error('selected row scope lost');
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
