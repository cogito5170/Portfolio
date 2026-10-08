// Live conversation with a character (CH-01..04), only when the page is served by `worldengine exhibit` and opened
// with ?talk=<url>. The key and the model live on that server; this page sends the visitor's words and shows replies.
// Nothing is stored here; the visitor id is random per page load and forgotten on reload.
export class TalkClient {
  constructor(url, eng) {
    this.url = url; this.eng = eng; this.sid = crypto.getRandomValues(new Uint32Array(2)).join('-'); this.box = null;
  }
  open(state) {
    if (this.box) { this.box.querySelector('input').focus(); return; }
    const f = document.createElement('form'); f.className = 'we-talk';
    f.innerHTML = '<input maxlength="300" placeholder="' + state.name + '에게 말 걸기" aria-label="말 걸기"><button>보내기</button><button type="button" aria-label="닫기">×</button>';
    f.lastChild.onclick = () => { f.remove(); this.box = null; };
    f.onsubmit = async e => {
      e.preventDefault(); const inp = f.querySelector('input'), text = inp.value.trim(); if (!text) return; inp.value = '';
      this.eng.caption('나: ' + text, null, 3);
      try {
        const r = await fetch(this.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sid: this.sid, character: state.name, text }) }).then(x => x.json());
        state.say(r.reply || r.error || '…');
      } catch (_) { state.say('지금은 대답할 수 없어요.'); }
    };
    document.body.appendChild(f); this.box = f; f.querySelector('input').focus();
  }
}
