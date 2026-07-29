// ==UserScript==
// @name         KSKDK_TTHC — Nhập liệu nhanh
// @namespace    https://quanlyskcd.medinet.org.vn/
// @version      1.1.0
// @description  Phím tắt + dán Excel + xuất CSV cho form Thông tin hành chính (KSKDK_TTHC)
// @match        https://quanlyskcd.medinet.org.vn/*
// @match        https://covid19.medinet.org.vn/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const FORM_CODE = 'KSKDK_TTHC';
  const API_BASE = 'https://be-qlskcd.medinet.org.vn';
  const HELP =
    'Ctrl+S Lưu | Ctrl+Enter Lưu+mới | Ctrl+Shift+E Xuất CSV | Ctrl+Shift+V Dán Excel | Alt+←/→ Field | F2 Focus | ? Help';

  let panel;
  let lastSchema = null;
  let statusTimer;

  function isTargetPage() {
    return /dynamicform\/viewer\/KSKDK_TTHC/i.test(location.pathname + location.hash);
  }

  function setStatus(msg, ok) {
    if (!panel) return;
    const el = panel.querySelector('.ksk-status');
    el.textContent = msg;
    el.style.color = ok === false ? '#b91c1c' : ok ? '#047857' : '#334155';
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      el.textContent = HELP;
      el.style.color = '#64748b';
    }, 4000);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function findViewerElement() {
    return (
      document.querySelector('dynamicformviewer') ||
      document.querySelector('dynamicFormViewer') ||
      document.querySelector('[class*="dynamic-form"]') ||
      document.querySelector('dx-form') ||
      document.querySelector('.dx-form')
    );
  }

  function getNgComponent(el) {
    if (!el || !window.ng) return null;
    try {
      if (typeof ng.getComponent === 'function') {
        let cur = el;
        while (cur) {
          const c = ng.getComponent(cur);
          if (c && (c.dynamicForm || c.onFormSubmit || c.formId)) return c;
          cur = cur.parentElement;
        }
      }
    } catch (_) {}
    return null;
  }

  function walkNgTree(root, depth, out) {
    if (!root || depth > 12 || !window.ng) return;
    try {
      const c = ng.getComponent(root);
      if (c && c.dynamicForm && c.dynamicForm.formFields) out.push(c);
    } catch (_) {}
    for (const child of root.children || []) walkNgTree(child, depth + 1, out);
  }

  function getFormComponent() {
    const host = findViewerElement();
    let comp = getNgComponent(host);
    if (comp) return comp;
    const found = [];
    walkNgTree(document.body, 0, found);
    return found.find((c) => {
      const code = (c.dynamicForm && (c.dynamicForm.code || c.dynamicForm.formCode)) || c.formCode || '';
      return String(code).toUpperCase() === FORM_CODE || /KSKDK_TTHC/i.test(location.pathname);
    }) || found[0] || null;
  }

  function getDxFormInstance() {
    const nodes = qsa('.dx-form');
    for (const n of nodes) {
      try {
        if (window.$ && $(n).dxForm) {
          const inst = $(n).dxForm('instance');
          if (inst) return inst;
        }
      } catch (_) {}
      if (n.dxForm && typeof n.dxForm === 'function') {
        try {
          return n.dxForm('instance');
        } catch (_) {}
      }
    }
    return null;
  }

  function editableFields(comp) {
    const fields = (comp && comp.dynamicForm && comp.dynamicForm.formFields) || [];
    return fields.filter((f) => {
      if (!f) return false;
      const t = String(f.fieldType || f.editorType || '').toLowerCase();
      if (['label', 'group', 'tab', 'button', 'empty', 'html', 'separator', 'pagebreak'].includes(t)) return false;
      if (f.visible === false || f.isVisible === false) return false;
      const name = f.dataField || f.fieldName || f.code || f.name;
      return !!name;
    });
  }

  function getSchema(comp) {
    const fields = editableFields(comp).map((f, idx) => ({
      stt: idx + 1,
      dataField: f.dataField || f.fieldName || f.code || f.name,
      label: (f.label && (f.label.text || f.label)) || f.caption || f.title || f.dataField || '',
      fieldType: f.fieldType || f.editorType || '',
      required: !!(f.isRequired || f.required || (f.validationRules || []).some((r) => r && r.type === 'required')),
    }));
    lastSchema = {
      formCode: FORM_CODE,
      formId: (comp && (comp.formId || (comp.dynamicForm && comp.dynamicForm.id))) || 1000092,
      name: (comp && comp.dynamicForm && (comp.dynamicForm.name || comp.dynamicForm.title)) || 'Thông tin hành chính',
      siteId: sessionStorage.getItem('PORTAL_SESSIONSITEID') || '',
      exportedAt: new Date().toISOString(),
      fields,
      sampleFormData: (comp && comp.dynamicForm && comp.dynamicForm.formData) || {},
    };
    return lastSchema;
  }

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  function csvEscape(v) {
    const s = v == null ? '' : String(v);
    if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function exportCsv(comp) {
    const schema = getSchema(comp);
    if (!schema.fields.length) {
      setStatus('Không đọc được field — mở form và đợi load xong rồi thử lại.', false);
      return;
    }
    const headers = schema.fields.map((f) => f.dataField);
    const labels = schema.fields.map((f) => f.label);
    const sample = schema.fields.map((f) => {
      const v = schema.sampleFormData[f.dataField];
      return v == null ? '' : v;
    });
    const lines = [
      headers.map(csvEscape).join(','),
      labels.map(csvEscape).join(','),
      sample.map(csvEscape).join(','),
    ];
    downloadText('KSKDK_TTHC_mau.csv', '\uFEFF' + lines.join('\n'), 'text/csv;charset=utf-8');
    downloadText('KSKDK_TTHC_schema.json', JSON.stringify(schema, null, 2), 'application/json');
    setStatus('Đã xuất CSV + schema (' + schema.fields.length + ' field).', true);
  }

  function setFormValues(comp, rowObj) {
    if (!comp || !comp.dynamicForm) return 0;
    if (!comp.dynamicForm.formData) comp.dynamicForm.formData = {};
    let n = 0;
    Object.keys(rowObj).forEach((k) => {
      if (k.startsWith('_')) return;
      comp.dynamicForm.formData[k] = rowObj[k];
      n++;
    });
    const dx = getDxFormInstance();
    if (dx && typeof dx.option === 'function') {
      try {
        dx.option('formData', Object.assign({}, comp.dynamicForm.formData));
        dx.repaint && dx.repaint();
      } catch (_) {}
    }
    try {
      if (comp.cdr && comp.cdr.detectChanges) comp.cdr.detectChanges();
    } catch (_) {}
    return n;
  }

  function parseTsvOrCsv(text) {
    const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').filter((l) => l.trim() !== '');
    if (!lines.length) return null;
    const delim = lines[0].includes('\t') ? '\t' : ',';
    const split = (line) => {
      if (delim === '\t') return line.split('\t');
      const out = [];
      let cur = '';
      let q = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
          if (q && line[i + 1] === '"') {
            cur += '"';
            i++;
          } else q = !q;
        } else if (ch === ',' && !q) {
          out.push(cur);
          cur = '';
        } else cur += ch;
      }
      out.push(cur);
      return out;
    };
    return lines.map(split);
  }

  async function pasteFromClipboard(comp) {
    let text = '';
    try {
      text = await navigator.clipboard.readText();
    } catch (_) {
      text = prompt('Dán 1 dòng Excel (có thể gồm dòng tiêu đề dataField):', '') || '';
    }
    if (!text.trim()) return;
    const table = parseTsvOrCsv(text);
    if (!table || !table.length) {
      setStatus('Clipboard trống hoặc không parse được.', false);
      return;
    }
    const schema = getSchema(comp);
    let headers;
    let values;
    if (table.length >= 2) {
      const first = table[0].map((h) => h.trim());
      const looksLikeHeader = first.some((h) => schema.fields.some((f) => f.dataField === h));
      if (looksLikeHeader) {
        headers = first;
        values = table[1];
      } else {
        headers = schema.fields.map((f) => f.dataField);
        values = table[0];
      }
    } else {
      headers = schema.fields.map((f) => f.dataField);
      values = table[0];
    }
    const row = {};
    headers.forEach((h, i) => {
      if (!h) return;
      row[h] = values[i] != null ? String(values[i]).trim() : '';
    });
    const n = setFormValues(comp, row);
    setStatus('Đã dán ' + n + ' giá trị vào form.', true);
  }

  function clickButtonByText(texts) {
    const buttons = qsa('dx-button, .dx-button, button');
    for (const b of buttons) {
      const t = (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim();
      if (texts.some((x) => t === x || t.includes(x))) {
        b.click();
        return t;
      }
    }
    return null;
  }

  function saveForm(comp) {
    if (comp && typeof comp.onFormSubmit === 'function') {
      try {
        comp.onFormSubmit(null, null, false, false, false);
        setStatus('Đã gọi Lưu (onFormSubmit).', true);
        return;
      } catch (e) {
        console.warn(e);
      }
    }
    const clicked = clickButtonByText(['Lưu', 'Save']);
    if (clicked) setStatus('Đã bấm nút: ' + clicked, true);
    else setStatus('Không tìm thấy nút Lưu.', false);
  }

  function saveAndNew(comp) {
    saveForm(comp);
    setTimeout(() => {
      const clicked = clickButtonByText(['Thêm mới', 'Tạo mới', 'Làm trống', 'Nhập mới']);
      if (clicked) setStatus('Lưu xong → ' + clicked, true);
    }, 800);
  }

  function focusableInputs() {
    return qsa(
      '.dx-texteditor-input, input:not([type=hidden]):not([disabled]), textarea:not([disabled]), select:not([disabled])'
    ).filter((el) => el.offsetParent !== null);
  }

  function focusField(delta) {
    const inputs = focusableInputs();
    if (!inputs.length) return;
    const active = document.activeElement;
    let idx = inputs.indexOf(active);
    if (idx < 0) idx = delta > 0 ? -1 : 0;
    const next = inputs[(idx + delta + inputs.length) % inputs.length];
    next.focus();
    if (typeof next.select === 'function') {
      try {
        next.select();
      } catch (_) {}
    }
  }

  function getAuthInfo() {
    const siteId = sessionStorage.getItem('PORTAL_SESSIONSITEID') || '';
    const raw = localStorage.getItem('1_keys');
    let keys = null;
    try {
      keys = raw ? JSON.parse(raw) : null;
    } catch (_) {}
    return { siteId, keys, apiBase: API_BASE, formCode: FORM_CODE, formId: 1000092 };
  }

  function copyAuthHint() {
    const info = getAuthInfo();
    const text = JSON.stringify(
      {
        note: 'enc_tk trong 1_keys là token đã mã hóa AES của app. Cách dễ: F12 → Network → chọn request API → copy header Authorization và SessionSiteId.',
        siteId: info.siteId,
        formId: info.formId,
        formCode: info.formCode,
        apiBase: info.apiBase,
        localStorage_1_keys: info.keys,
      },
      null,
      2
    );
    navigator.clipboard.writeText(text).then(
      () => setStatus('Đã copy thông tin auth/site vào clipboard.', true),
      () => {
        prompt('Copy nội dung này:', text);
      }
    );
  }

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'kskdk-tthc-helper';
    panel.innerHTML =
      '<div class="ksk-title">KSKDK_TTHC nhập nhanh</div>' +
      '<div class="ksk-status">' +
      HELP +
      '</div>' +
      '<div class="ksk-actions">' +
      '<button type="button" data-act="save">Lưu</button>' +
      '<button type="button" data-act="export">Xuất CSV</button>' +
      '<button type="button" data-act="paste">Dán Excel</button>' +
      '<button type="button" data-act="auth">Copy token/site</button>' +
      '<button type="button" data-act="hide">Ẩn</button>' +
      '</div>';
    const style = document.createElement('style');
    style.textContent =
      '#kskdk-tthc-helper{position:fixed;right:12px;bottom:12px;z-index:2147483646;width:320px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.18);font:13px/1.4 system-ui,Segoe UI,sans-serif;color:#0f172a;padding:10px 12px}' +
      '#kskdk-tthc-helper .ksk-title{font-weight:700;margin-bottom:6px}' +
      '#kskdk-tthc-helper .ksk-status{font-size:12px;color:#64748b;min-height:34px;margin-bottom:8px}' +
      '#kskdk-tthc-helper .ksk-actions{display:flex;flex-wrap:wrap;gap:6px}' +
      '#kskdk-tthc-helper button{border:1px solid #94a3b8;background:#f8fafc;border-radius:6px;padding:4px 8px;cursor:pointer}' +
      '#kskdk-tthc-helper button:hover{background:#e2e8f0}';
    document.documentElement.appendChild(style);
    document.documentElement.appendChild(panel);
    panel.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-act]');
      if (!btn) return;
      const act = btn.getAttribute('data-act');
      const comp = getFormComponent();
      if (act === 'hide') {
        panel.style.display = 'none';
        return;
      }
      if (act === 'save') saveForm(comp);
      if (act === 'export') exportCsv(comp);
      if (act === 'paste') pasteFromClipboard(comp);
      if (act === 'auth') copyAuthHint();
    });
    return panel;
  }

  function onKeyDown(e) {
    if (!isTargetPage()) return;
    const tag = (e.target && e.target.tagName) || '';
    const typing = /INPUT|TEXTAREA|SELECT/.test(tag) || (e.target && e.target.isContentEditable);

    if (e.key === '?' && !typing && !e.ctrlKey && !e.altKey && !e.metaKey) {
      ensurePanel();
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      return;
    }

    const comp = getFormComponent();

    if (e.ctrlKey && !e.shiftKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      e.stopPropagation();
      saveForm(comp);
      return;
    }
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      saveAndNew(comp);
      return;
    }
    if (e.ctrlKey && e.shiftKey && (e.key === 'E' || e.key === 'e')) {
      e.preventDefault();
      exportCsv(comp);
      return;
    }
    if (e.ctrlKey && e.shiftKey && (e.key === 'V' || e.key === 'v')) {
      e.preventDefault();
      pasteFromClipboard(comp);
      return;
    }
    if (e.altKey && e.key === 'ArrowRight') {
      e.preventDefault();
      focusField(1);
      return;
    }
    if (e.altKey && e.key === 'ArrowLeft') {
      e.preventDefault();
      focusField(-1);
      return;
    }
    if (e.key === 'F2') {
      e.preventDefault();
      const inputs = focusableInputs();
      if (inputs[0]) inputs[0].focus();
    }
  }

  function boot() {
    if (!isTargetPage()) return;
    ensurePanel();
    setStatus('Sẵn sàng trên form ' + FORM_CODE, true);
  }

  document.addEventListener('keydown', onKeyDown, true);
  boot();
  window.addEventListener('hashchange', boot);
  const mo = new MutationObserver(() => {
    if (isTargetPage() && !document.getElementById('kskdk-tthc-helper')) ensurePanel();
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
