// Captions (XR-11): every sound, character line, trigger caption and tour stop is shown as text. The log is kept
// (eng.captionLog) so tests can check that what was heard was also shown.
const CSS = `.we-cap{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(max(10px,env(safe-area-inset-bottom)) + 64px);max-width:min(640px,calc(100vw - 24px));
 background:#000000c0;color:#fff;font:16px/1.45 "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif;padding:8px 14px;border-radius:12px;text-align:center;pointer-events:none;z-index:6}
.we-cap:empty{display:none}`;

export class Captions {
  constructor(parent) {
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    this.el = document.createElement('div'); this.el.className = 'we-cap'; this.el.setAttribute('aria-live', 'polite'); this.el.setAttribute('role', 'status');
    parent.appendChild(this.el); this.timer = null;
  }
  show(text, seconds = 4) {
    this.el.textContent = text; clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.el.textContent = ''; }, seconds * 1000);
  }
}
