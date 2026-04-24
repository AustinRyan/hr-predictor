/* =========================================================
   HOMERUN — landing + rankings app logic
   ========================================================= */
(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  const clamp = (v,a,b) => Math.max(a, Math.min(b,v));
  const lerp = (a,b,t) => a + (b-a)*t;

  const state = {
    minProb: 3.0,
    sort: 'prob',
    team: '',
    limit: 20,
    parlay: [],      // array of pick ids
    tweaks: { ...(window.__TWEAK_DEFAULTS || {}) }
  };

  /* ---------- DATE / CLOCK ---------- */
  function fmtDate() {
    const d = new Date();
    return d.toLocaleDateString('en-US', { weekday:'long', month:'long', day:'numeric' }).toUpperCase();
  }
  function fmtClock() {
    const d = new Date();
    return d.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', hour12:false });
  }
  $('#today-date').textContent = fmtDate();
  $('#app-date').textContent = fmtDate();
  const clockEl = $('#nav-clock');
  function tickClock() { clockEl.textContent = `LIVE · ${fmtClock()}`; }
  tickClock(); setInterval(tickClock, 1000);

  /* ---------- NAV solidify on scroll ---------- */
  const nav = $('#nav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('solid', window.scrollY > 40);
  }, { passive: true });

  /* ---------- TICKER ---------- */
  (function fillTicker() {
    const track = $('#ticker-track');
    const items = window.HR_DATA.ticker;
    const oneLoop = items.map(t => `<span class="t-item"><span class="t-dot">◆</span>${t}</span>`).join('');
    track.innerHTML = oneLoop + oneLoop; // double for seamless loop
  })();

  /* ---------- SCOREBOARD LEDS ---------- */
  (function fillLeds() {
    const el = $('#leds');
    el.innerHTML = window.HR_DATA.scoreboard.map(g => `
      <div class="led">
        <div class="led-top">
          <span>${g.time} ET</span>
          <span>LIVE FEED</span>
        </div>
        <div class="led-row">
          <div class="led-team">
            <div class="led-abbr">${g.away}</div>
            <div class="led-info">
              <span class="led-name">AWAY</span>
              <span class="led-sub">PROJ 4.2 R</span>
            </div>
          </div>
        </div>
        <div class="led-row">
          <div class="led-team">
            <div class="led-abbr">${g.home}</div>
            <div class="led-info">
              <span class="led-name">HOME</span>
              <span class="led-sub">PROJ 4.8 R</span>
            </div>
          </div>
        </div>
        <div class="led-row">
          <div class="led-info">
            <span class="led-sub">TOP HR PICK</span>
            <span class="led-name">${g.topProb}</span>
          </div>
        </div>
      </div>
    `).join('');
  })();

  /* ---------- COUNT-UP NUMBERS (on reveal) ---------- */
  function animateCount(el) {
    const target = parseFloat(el.dataset.count);
    const decimals = parseInt(el.dataset.decimals || '0', 10);
    const dur = 1400;
    const start = performance.now();
    function step(t) {
      const p = clamp((t-start)/dur, 0, 1);
      const eased = 1 - Math.pow(1-p, 3);
      const cur = target * eased;
      el.textContent = cur.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  const probCountEl = $('.hero .prob-big');
  function animateProb() {
    const target = parseFloat(probCountEl.dataset.count);
    const dur = 1600;
    const start = performance.now();
    function step(t) {
      const p = clamp((t-start)/dur, 0, 1);
      const eased = 1 - Math.pow(1-p, 3);
      const cur = (target * eased).toFixed(1);
      probCountEl.innerHTML = cur + '<span class="pct">%</span>';
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  setTimeout(animateProb, 900);

  /* ---------- REVEAL + count-up on scroll ---------- */
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        $$('.stat-num[data-count]', e.target).forEach(n => {
          if (!n.dataset.done) { n.dataset.done = '1'; animateCount(n); }
        });
        io.unobserve(e.target);
      }
    });
  }, { threshold: .15 });
  $$('.scoreboard, .arc, .how, .handoff, .app, .section-head').forEach(el => {
    el.classList.add('reveal');
    io.observe(el);
  });

  /* ---------- SIGNATURE: BALL ARC scroll-linked ---------- */
  const arcStage   = $('#arc-stage');
  const arcPath    = $('#arc-path');
  const arcBall    = $('#arc-ball');
  const arcMarkers = $('#arc-markers');
  const captions   = $$('.arc-caption');
  const pathLen    = 1000;

  // place trail markers along the path with probability labels
  const markerData = [
    { at: 0.12, v: '108.3 MPH' },
    { at: 0.26, v: '28.4°' },
    { at: 0.42, v: '+1.4 MPH WIND' },
    { at: 0.58, v: '+6% PARK' },
    { at: 0.78, v: '14.8% P(HR)' }
  ];
  markerData.forEach((m, i) => {
    const pt = arcPath.getPointAtLength(m.at * arcPath.getTotalLength());
    const g = document.createElementNS('http://www.w3.org/2000/svg','g');
    g.setAttribute('class','arc-marker');
    g.setAttribute('data-at', m.at);
    g.innerHTML = `
      <circle cx="${pt.x}" cy="${pt.y}" r="4" opacity="0"/>
      <text x="${pt.x + 10}" y="${pt.y - 10}" opacity="0">${m.v}</text>
    `;
    arcMarkers.appendChild(g);
  });
  const markerEls = $$('#arc-markers .arc-marker');

  function updateArc() {
    const rect = arcStage.getBoundingClientRect();
    const stageH = rect.height - window.innerHeight;
    const progress = clamp((-rect.top) / stageH, 0, 1);

    // reveal path via dashoffset (1000 -> 0)
    arcPath.setAttribute('stroke-dashoffset', (1 - progress) * pathLen);

    // move ball along path
    const totalLen = arcPath.getTotalLength();
    const pt = arcPath.getPointAtLength(progress * totalLen);
    arcBall.setAttribute('transform', `translate(${pt.x},${pt.y}) rotate(${progress * 720})`);

    // reveal markers one by one
    markerEls.forEach(g => {
      const at = parseFloat(g.dataset.at);
      const show = progress >= at;
      g.querySelector('circle').setAttribute('opacity', show ? '1' : '0');
      g.querySelector('text').setAttribute('opacity', show ? '1' : '0');
    });

    // captions
    captions.forEach(c => {
      const from = parseFloat(c.dataset.from);
      const to   = parseFloat(c.dataset.to);
      c.classList.toggle('active', progress >= from && progress < to);
    });
  }
  window.addEventListener('scroll', updateArc, { passive: true });
  window.addEventListener('resize', updateArc);
  requestAnimationFrame(updateArc);

  /* ---------- TEAM FILTER options ---------- */
  (function initTeamFilter() {
    const sel = $('#team-filter');
    window.HR_DATA.teams.sort().forEach(t => {
      const o = document.createElement('option');
      o.value = t; o.textContent = t;
      sel.appendChild(o);
    });
    sel.addEventListener('change', e => { state.team = e.target.value; renderRows(); });
  })();

  /* ---------- RANKINGS TABLE ---------- */
  function probBarW(p) { return Math.min(100, p * 6) + '%'; } // 16.6% -> 100% width
  function edgeClass(e) { return e.startsWith('+') ? 'pos' : (e.startsWith('-') ? 'neg' : ''); }

  function sortedPicks() {
    const picks = window.HR_DATA.picks.filter(p =>
      p.prob >= state.minProb &&
      (!state.team || p.team === state.team || p.vsTeam === state.team)
    );
    picks.sort((a,b) => {
      if (state.sort === 'prob') return b.prob - a.prob;
      if (state.sort === 'expected_hrs') return b.ehr - a.ehr;
      if (state.sort === 'edge') {
        const ea = parseFloat(a.edge), eb = parseFloat(b.edge);
        return eb - ea;
      }
      return 0;
    });
    return picks.slice(0, state.limit);
  }

  function renderRows() {
    const body = $('#rk-body');
    const rows = sortedPicks();
    body.innerHTML = rows.map((p, i) => {
      const isTop = i < 3;
      const inParlay = state.parlay.includes(p.id);
      const ctxHtml = p.ctx.map(c => {
        const cls = c.pos ? 'pos' : (c.neg ? 'neg' : '');
        return `<span class="rk-ctx-chip ${cls}">${c.k} ${c.v}</span>`;
      }).join('');
      return `
        <div class="rk-row ${isTop ? 'top3' : ''}" data-id="${p.id}-${i}">
          <div class="rk-c rk-c-rank rk-rank">${String(i+1).padStart(2,'0')}</div>
          <div class="rk-c rk-c-player rk-player">
            <div class="rk-avatar"><span class="rk-avatar-num">${p.num}</span></div>
            <div>
              <div class="rk-pl-name">${p.first} ${p.last}</div>
              <div class="rk-pl-meta">
                <span class="rk-team">${p.team}</span>
                <span>${p.pos}</span>
                <span>${p.hand}</span>
              </div>
            </div>
          </div>
          <div class="rk-c rk-c-match rk-match">
            <div class="rk-match-top">vs ${p.vs}</div>
            <div class="rk-match-bot">${p.park} · ${p.time}</div>
          </div>
          <div class="rk-c rk-c-ctx rk-ctx">${ctxHtml}</div>
          <div class="rk-c rk-c-prob rk-prob">
            <div class="rk-prob-pct">${p.prob.toFixed(1)}%</div>
            <div class="rk-prob-bar"><span style="width:${probBarW(p.prob)}"></span></div>
          </div>
          <div class="rk-c rk-c-ehr rk-ehr">${p.ehr.toFixed(3)}</div>
          <div class="rk-c rk-c-edge rk-edge ${edgeClass(p.edge)}">${p.edge}</div>
          <div class="rk-c rk-c-add">
            <button class="rk-add ${inParlay ? 'added' : ''}" data-add="${i}" aria-label="Add to parlay">${inParlay ? '✓' : '+'}</button>
          </div>
        </div>
      `;
    }).join('');

    $$('.rk-add', body).forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const idx = +btn.dataset.add;
        togglePickInParlay(rows[idx]);
      });
    });
  }

  /* ---------- FILTERS ---------- */
  $$('.seg-btn[data-sort]').forEach(b => {
    b.addEventListener('click', () => {
      $$('.seg-btn[data-sort]').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.sort = b.dataset.sort;
      renderRows();
    });
  });
  $$('.seg-btn[data-limit]').forEach(b => {
    b.addEventListener('click', () => {
      $$('.seg-btn[data-limit]').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.limit = +b.dataset.limit;
      renderRows();
    });
  });
  const minProbInput = $('#min-prob');
  const minProbVal = $('#min-prob-val');
  minProbInput.addEventListener('input', e => {
    state.minProb = parseFloat(e.target.value);
    minProbVal.textContent = state.minProb.toFixed(1) + '%';
    renderRows();
  });

  /* ---------- PARLAY ---------- */
  function togglePickInParlay(p) {
    const key = p.id + '-' + p.last;
    const i = state.parlay.findIndex(x => x.key === key);
    if (i >= 0) state.parlay.splice(i,1);
    else state.parlay.push({ key, first:p.first, last:p.last, team:p.team, vs:p.vs, prob:p.prob });
    renderParlay();
    renderRows();
  }
  function renderParlay() {
    const empty = $('#parlay-empty');
    const legsEl = $('#parlay-legs');
    const sum = $('#parlay-summary');
    const cnt = $('#parlay-count');
    const cta = $('#parlay-cta');

    cnt.textContent = state.parlay.length === 0 ? '0 legs' :
                      state.parlay.length + ' leg' + (state.parlay.length>1?'s':'');

    if (state.parlay.length === 0) {
      empty.style.display = '';
      legsEl.innerHTML = '';
      $('#ps-prob').textContent = '—';
      $('#ps-odds').textContent = '—';
      $('#ps-pays').textContent = '—';
      cta.disabled = true;
      return;
    }
    empty.style.display = 'none';

    legsEl.innerHTML = state.parlay.map((l, i) => `
      <div class="leg">
        <div>
          <div class="leg-name">${l.first.charAt(0)}. ${l.last}</div>
          <div class="leg-match">${l.team} · vs ${l.vs}</div>
        </div>
        <div class="leg-prob">${l.prob.toFixed(1)}%</div>
        <button class="leg-rm" data-rm="${i}">remove</button>
      </div>
    `).join('');
    $$('.leg-rm', legsEl).forEach(b => b.addEventListener('click', () => {
      state.parlay.splice(+b.dataset.rm, 1);
      renderParlay(); renderRows();
    }));

    // combined prob (independence approximation)
    const combined = state.parlay.reduce((acc, l) => acc * (l.prob / 100), 1);
    const fairOdds = combined > 0 ? (1 / combined) : 0;
    const americanOdds = fairOdds >= 2 ? '+' + Math.round((fairOdds - 1) * 100) : Math.round(-100 / (fairOdds - 1));
    const pays = 100 * (fairOdds - 1);

    $('#ps-prob').textContent = (combined * 100).toFixed(2) + '%';
    $('#ps-odds').textContent = isFinite(fairOdds) ? (typeof americanOdds === 'number' ? (americanOdds>0?'+':'')+americanOdds : americanOdds) : '—';
    $('#ps-pays').textContent = '$' + pays.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    cta.disabled = false;
  }
  $('#parlay-clear').addEventListener('click', () => {
    state.parlay = []; renderParlay(); renderRows();
  });

  /* ---------- TABS (cosmetic) ---------- */
  $$('.tab').forEach(t => t.addEventListener('click', () => {
    $$('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
  }));

  /* ---------- REFRESH counter ---------- */
  (function refreshTimer() {
    const el = $('#refresh-btn');
    let left = 90;
    setInterval(() => {
      left--;
      if (left <= 0) left = 90;
      const mm = String(Math.floor(left/60)).padStart(2,'0');
      const ss = String(left%60).padStart(2,'0');
      el.innerHTML = `<span class="refresh-icon">↻</span> REFRESH · ${mm}:${ss}`;
    }, 1000);
  })();

  /* ---------- TWEAKS ---------- */
  function applyTweaks() {
    const { accent, intensity, grain } = state.tweaks;
    document.body.dataset.accent = accent;
    document.body.dataset.intensity = intensity;
    document.documentElement.style.setProperty('--grain-op', (grain/100 * .18).toFixed(3));
    $$('#swatches button').forEach(b => b.classList.toggle('active', b.dataset.accent === accent));
    $$('#intensity-seg button').forEach(b => b.classList.toggle('active', b.dataset.intensity === intensity));
    $('#grain-range').value = grain;
  }
  applyTweaks();

  $$('#swatches button').forEach(b => b.addEventListener('click', () => {
    state.tweaks.accent = b.dataset.accent;
    applyTweaks();
    postEdits();
  }));
  $$('#intensity-seg button').forEach(b => b.addEventListener('click', () => {
    state.tweaks.intensity = b.dataset.intensity;
    applyTweaks();
    postEdits();
  }));
  $('#grain-range').addEventListener('input', e => {
    state.tweaks.grain = +e.target.value;
    applyTweaks();
    postEdits();
  });
  function postEdits() {
    try { window.parent.postMessage({ type:'__edit_mode_set_keys', edits: state.tweaks }, '*'); } catch(e){}
  }

  // tweaks host protocol
  const tweaksEl = $('#tweaks');
  window.addEventListener('message', (e) => {
    if (!e.data) return;
    if (e.data.type === '__activate_edit_mode')   tweaksEl.hidden = false;
    if (e.data.type === '__deactivate_edit_mode') tweaksEl.hidden = true;
  });
  try { window.parent.postMessage({ type:'__edit_mode_available' }, '*'); } catch(e){}

  /* ---------- INITIAL RENDER ---------- */
  renderRows();
  renderParlay();
})();
